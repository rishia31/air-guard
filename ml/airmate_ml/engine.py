"""Serving: turn a person's last week of readings and logs into a risk assessment."""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch

from .aqi import category
from .explain import RiskExplainer
from .features import bin_end_hours, bin_series, build_timeline
from .model import AirmateRiskNet
from .rules import rule_score
from .schema import (
    BINS_PER_DAY,
    CTX_FEATURES,
    GROUP_LABELS,
    HISTORY_DAYS,
    HORIZON_HOURS,
    OUTDOOR,
    SCORE_HORIZON_INDEX,
    SENSOR_GROUPS,
    SENSORS,
    SEQ_FEATURES,
    TRIGGERS,
    WINDOW_BINS,
    band_for,
)

log = logging.getLogger(__name__)
DEFAULT_ARTIFACT = Path(__file__).resolve().parent / "artifacts" / "airmate_risk.pt"
N_BINS = HISTORY_DAYS * BINS_PER_DAY


@dataclass
class History:
    now: float  # epoch seconds
    reading_ts: np.ndarray  # (n,) epoch seconds
    readings: np.ndarray  # (n, 6) in SENSORS order, NaN where a sensor is absent
    puff_ts: np.ndarray = field(default_factory=lambda: np.zeros(0))
    puff_counts: np.ndarray = field(default_factory=lambda: np.zeros(0))
    symptom_ts: np.ndarray = field(default_factory=lambda: np.zeros(0))
    outdoor: dict = field(default_factory=dict)  # aqi, pollen, temp_c, humidity (None if unknown)
    triggers: Sequence[str] = ()
    utc_offset_seconds: float = 0.0


class RiskEngine:
    """Loads the trained model if present; otherwise falls back to the rule-based score."""

    def __init__(self, artifact: str | Path | None = None, explain_samples: int = 24):
        path = Path(artifact or os.environ.get("AIRMATE_MODEL_PATH") or DEFAULT_ARTIFACT)
        self.model: AirmateRiskNet | None = None
        self.explainer: RiskExplainer | None = None
        self.meta: dict = {"name": "rules", "trained_on": None}
        if not path.exists():
            log.warning("No model artifact at %s; using the rule-based score", path)
            return
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
        if list(ckpt["seq_features"]) != list(SEQ_FEATURES) or list(ckpt["ctx_features"]) != list(CTX_FEATURES):
            raise ValueError(f"{path} was trained with a different feature schema; retrain with `airmate-train`")
        self.model = AirmateRiskNet(**ckpt["config"])
        self.model.load_state_dict(ckpt["state_dict"])
        self.model.eval()
        self.explainer = RiskExplainer(self.model, n_samples=explain_samples)
        metrics = ckpt.get("metrics", {})
        self.meta = {
            "name": "airmate-gru-survival",
            "version": ckpt.get("version"),
            "trained_at": ckpt.get("trained_at"),
            "trained_on": "simulated cohort (no real patient data)",
            "test_auroc_4h": metrics.get("gru", {}).get("4h", {}).get("auroc"),
            "test_auprc_4h": metrics.get("gru", {}).get("4h", {}).get("auprc"),
        }

    @property
    def uses_model(self) -> bool:
        return self.model is not None

    def assess(self, history: History, explain: bool = True) -> dict:
        h = history
        sensors = bin_series(h.reading_ts, h.readings, h.now, N_BINS)
        puffs = bin_series(h.puff_ts, h.puff_counts, h.now, N_BINS, reduce="sum")[:, 0]
        symptoms = bin_series(h.symptom_ts, np.ones(len(h.symptom_ts)), h.now, N_BINS, reduce="sum")[:, 0]
        outdoor_now = np.array([np.nan if h.outdoor.get(k) is None else float(h.outdoor[k]) for k in OUTDOOR])
        reported = np.array([1.0 if t in set(h.triggers) else 0.0 for t in TRIGGERS])
        tl = build_timeline(
            sensors,
            bin_end_hours(h.now, N_BINS, h.utc_offset_seconds),
            puffs,
            symptoms,
            np.tile(outdoor_now, (N_BINS, 1)),
            reported,
        )

        available = [g for g, m in tl.masks.items() if m[-1]]
        latest = {}
        for group, names in SENSOR_GROUPS.items():
            for name in names:
                latest[name] = round(float(tl.raw[-1, SENSORS.index(name)]), 1) if group in available else None
        normal = {
            "pm25": float(tl.normal["pm25"][-1]),
            "pm10": float(tl.normal["pm25"][-1] + tl.normal["coarse"][-1]),
            "tvoc": float(tl.normal["tvoc"][-1]),
        }
        puffs_24h = float(puffs[-BINS_PER_DAY:].sum())
        symptoms_24h = float(symptoms[-BINS_PER_DAY:].sum())
        rule, rule_points = rule_score(latest, h.outdoor, puffs_24h, symptoms_24h, h.triggers)

        result: dict = {
            "rule_score": round(rule),
            "latest": latest,
            "normal": {k: round(v, 1) for k, v in normal.items()},
            "ratios": _ratios(latest, normal),
            "sensors_available": available,
            "outdoor": {k: h.outdoor.get(k) for k in OUTDOOR},
            "puffs_24h": int(puffs_24h),
            "symptoms_24h": int(symptoms_24h),
            "model": self.meta,
        }

        if self.model is None:
            score = rule
            result.update(probabilities=None, normal_day_score=None)
            contributions = dict(rule_points)
        else:
            seq = torch.from_numpy(tl.seq[-WINDOW_BINS:][None])
            ctx = torch.from_numpy(tl.ctx[-1:])
            with torch.no_grad():
                probs = self.model.cumulative_risk(seq, ctx)[0].numpy()
            score = 100.0 * float(probs[SCORE_HORIZON_INDEX])
            result["probabilities"] = {f"{hh}h": round(float(p), 4) for hh, p in zip(HORIZON_HOURS, probs, strict=True)}
            contributions = {}
            result["normal_day_score"] = None
            if explain and self.explainer is not None:
                values, _, normal_day = self.explainer.explain(seq, ctx)
                contributions = {g: float(v) for g, v in zip(self.explainer.groups, values[0], strict=True)}
                result["normal_day_score"] = round(float(normal_day[0]), 1)

        result["score"] = int(round(score))
        result["band"] = band_for(score)
        result["factors"] = _factors(contributions, latest, normal, h.outdoor, puffs_24h, symptoms_24h, available)
        return result


def _ratios(latest: dict, normal: dict) -> dict:
    floors = {"pm25": 3.0, "pm10": 5.0, "tvoc": 50.0}
    out = {}
    for key, floor in floors.items():
        if latest.get(key) is not None:
            out[key] = round(latest[key] / max(normal[key], floor), 2)
    return out


def _fact(group: str, latest: dict, normal: dict, outdoor: dict, puffs_24h: float, symptoms_24h: float,
          available: list[str]) -> str | None:
    ratios = _ratios(latest, normal)
    if group == "dust" and "pm" in available:
        return f"Dust (PM10) is {ratios['pm10']:.1f}× your normal ({latest['pm10']:.0f} vs {normal['pm10']:.0f} µg/m³)"
    if group == "smoke" and "pm" in available:
        return (f"Fine particles (PM2.5) are {ratios['pm25']:.1f}× your normal "
                f"({latest['pm25']:.0f} vs {normal['pm25']:.0f} µg/m³)")
    if group == "odors" and "voc" in available:
        return f"Chemical odors (TVOC) are {ratios['tvoc']:.1f}× your normal ({latest['tvoc']:.0f} ppb)"
    if group == "stuffy_air" and "co2" in available:
        return f"CO₂ is {latest['co2']:.0f} ppm; the room needs fresh air (outdoor air is about 420)"
    if group == "humidity" and "climate" in available:
        return f"Humidity is {latest['humidity']:.0f}%; mold and dust mites thrive above 60%"
    if group == "cold_air" and "climate" in available:
        return f"Indoor temperature is {latest['temp_c']:.1f} °C; cold air can tighten airways"
    if group == "pollen" and outdoor.get("pollen") is not None:
        level = ["none", "very low", "low", "moderate", "high", "very high"][int(round(min(max(outdoor["pollen"], 0), 5)))]
        return f"Pollen forecast is {level} ({outdoor['pollen']:.1f} of 5)"
    if group == "outdoor_air" and outdoor.get("aqi") is not None:
        return f"Outdoor AQI is {outdoor['aqi']:.0f} ({category(outdoor['aqi'])[0].lower()})"
    if group == "weather" and outdoor.get("temp_c") is not None:
        return f"It is {outdoor['temp_c']:.0f} °C outside with {outdoor.get('humidity') or 0:.0f}% humidity"
    if group == "inhaler_use" and puffs_24h > 0:
        return f"You used your rescue inhaler {int(puffs_24h)} time{'s' if puffs_24h != 1 else ''} in the last 24 hours"
    if group == "symptoms" and symptoms_24h > 0:
        return f"You logged {int(symptoms_24h)} symptom{'s' if symptoms_24h != 1 else ''} in the last 24 hours"
    if group == "time_of_day":
        return "Asthma symptoms are often worse at night and in the early morning"
    return None


def _factors(contributions: dict, latest, normal, outdoor, puffs_24h, symptoms_24h, available) -> list[dict]:
    factors = []
    for group, points in sorted(contributions.items(), key=lambda kv: -kv[1]):
        if points < 0.5:
            continue
        factors.append(
            {
                "key": group,
                "label": GROUP_LABELS.get(group, group),
                "points": round(points, 1),
                "detail": _fact(group, latest, normal, outdoor, puffs_24h, symptoms_24h, available),
            }
        )
    return factors[:5]
