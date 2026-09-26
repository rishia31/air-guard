"""Transparent rule-based risk score.

Used as the fallback when no trained model is available, and as the baseline
the learned model is evaluated against. Thresholds follow EPA AQI breakpoints
for particles and common indoor guidance for CO2, TVOC, and humidity.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

REPORTED_MULTIPLIER = 1.8

# component -> (trigger that amplifies it, max points)
COMPONENTS = {
    "dust": ("dust", 30.0),
    "smoke": ("smoke", 30.0),
    "odors": ("odors", 20.0),
    "stuffy_air": (None, 10.0),
    "humidity": ("humidity", 15.0),
    "cold_air": ("cold_air", 10.0),
    "pollen": ("pollen", 20.0),
    "outdoor_air": ("smoke", 15.0),
    "inhaler_use": (None, 15.0),
    "symptoms": (None, 10.0),
}


def _clip01(x):
    return np.clip(np.nan_to_num(x, nan=0.0), 0.0, 1.0)


def rule_components(pm25, pm10, co2, tvoc, temp_c, humidity, pollen, aqi, puffs_24h, symptoms_24h, reported):
    """Points per component. Inputs may be scalars or equal-length arrays; NaN means unknown.

    ``reported`` maps trigger name -> 0/1 (scalar or array).
    """
    coarse = np.maximum(np.asarray(pm10, dtype=float) - np.nan_to_num(pm25), 0.0)
    level = {
        "dust": _clip01((coarse - 20) / 130),
        "smoke": _clip01((np.asarray(pm25, dtype=float) - 9) / 46),
        "odors": _clip01((np.asarray(tvoc, dtype=float) - 220) / 1980),
        "stuffy_air": _clip01((np.asarray(co2, dtype=float) - 1000) / 1000),
        "humidity": np.clip(
            _clip01((np.asarray(humidity, dtype=float) - 60) / 20) + _clip01((30 - np.asarray(humidity, dtype=float)) / 15), 0, 1
        ),
        "cold_air": _clip01((18 - np.asarray(temp_c, dtype=float)) / 5),
        "pollen": _clip01((np.asarray(pollen, dtype=float) - 2) / 3),
        "outdoor_air": _clip01((np.asarray(aqi, dtype=float) - 50) / 100),
        "inhaler_use": _clip01(np.asarray(puffs_24h, dtype=float) / 6),
        "symptoms": _clip01(np.asarray(symptoms_24h, dtype=float) / 3),
    }
    points = {}
    for name, (trigger, max_points) in COMPONENTS.items():
        mult = 1.0 if trigger is None else 1.0 + (REPORTED_MULTIPLIER - 1.0) * np.asarray(reported.get(trigger, 0.0))
        points[name] = level[name] * max_points * mult
    return points


def score_from_points(points: dict) -> np.ndarray:
    total = sum(points.values())
    return 100.0 * (1.0 - np.exp(-np.asarray(total) / 60.0))


def rule_score(
    latest: dict, outdoor: dict, puffs_24h: float, symptoms_24h: float, triggers: Iterable[str]
) -> tuple[float, dict[str, float]]:
    """Score one moment. ``latest`` holds sensor readings (None if the sensor is absent)."""

    def get(d: dict, key: str) -> float:
        value = d.get(key)
        return float("nan") if value is None else float(value)

    trig = set(triggers)
    points = rule_components(
        get(latest, "pm25"),
        get(latest, "pm10"),
        get(latest, "co2"),
        get(latest, "tvoc"),
        get(latest, "temp_c"),
        get(latest, "humidity"),
        get(outdoor, "pollen"),
        get(outdoor, "aqi"),
        puffs_24h,
        symptoms_24h,
        {t: 1.0 if t in trig else 0.0 for t in ("dust", "smoke", "pollen", "humidity", "odors", "cold_air")},
    )
    return float(score_from_points(points)), {k: float(v) for k, v in points.items()}
