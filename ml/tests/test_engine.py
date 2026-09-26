import numpy as np
import pytest
import torch

from airmate_ml.engine import DEFAULT_ARTIFACT, History, RiskEngine
from airmate_ml.rules import rule_score
from airmate_ml.schema import BIN_SECONDS, BINS_PER_DAY, HISTORY_DAYS, WINDOW_BINS, band_for

NOW = 1_790_000_000.0  # a fixed moment, 2026-09-21 UTC


def _history(spike: str | None = None, triggers=("dust",), sensors=("pm", "co2", "voc", "climate"), puffs=0) -> History:
    rng = np.random.default_rng(0)
    n = HISTORY_DAYS * BINS_PER_DAY
    ts = NOW - (n - 1 - np.arange(n)) * BIN_SECONDS
    base = np.array([6.0, 14.0, 650.0, 120.0, 22.0, 45.0])
    readings = base * (1 + 0.05 * rng.standard_normal((n, 6)))
    if spike == "dust":
        readings[-8:, 1] = 180.0
    elif spike == "odors":
        readings[-8:, 3] = 2500.0
    if "pm" not in sensors:
        readings[:, 0:2] = np.nan
    if "voc" not in sensors:
        readings[:, 3] = np.nan
    if "co2" not in sensors:
        readings[:, 2] = np.nan
    if "climate" not in sensors:
        readings[:, 4:6] = np.nan
    puff_ts = np.array([NOW - 3600.0 * 5]) if puffs else np.zeros(0)
    return History(
        now=NOW,
        reading_ts=ts,
        readings=readings,
        puff_ts=puff_ts,
        puff_counts=np.full(len(puff_ts), float(puffs)),
        outdoor={"aqi": 35, "pollen": 1.2, "temp_c": 21, "humidity": 50},
        triggers=list(triggers),
        utc_offset_seconds=-4 * 3600,
    )


def test_rule_score_rises_with_exposure_and_reported_triggers():
    calm = {"pm25": 6, "pm10": 14, "co2": 650, "tvoc": 120, "temp_c": 22, "humidity": 45}
    dusty = {**calm, "pm10": 180}
    outdoor = {"aqi": 35, "pollen": 1.2}
    s_calm, _ = rule_score(calm, outdoor, 0, 0, [])
    s_dusty, points = rule_score(dusty, outdoor, 0, 0, [])
    s_dusty_sensitive, _ = rule_score(dusty, outdoor, 0, 0, ["dust"])
    assert s_calm < 5 < s_dusty < s_dusty_sensitive <= 100
    assert max(points, key=points.get) == "dust"
    s_none, _ = rule_score({k: None for k in calm}, {}, 0, 0, [])
    assert s_none == 0


def test_band_thresholds():
    assert band_for(5) == "low" and band_for(30) == "elevated" and band_for(80) == "high"


def test_rules_fallback_without_artifact(tmp_path):
    engine = RiskEngine(artifact=tmp_path / "missing.pt")
    assert not engine.uses_model
    calm = engine.assess(_history())
    dusty = engine.assess(_history("dust"))
    assert calm["probabilities"] is None and calm["model"]["name"] == "rules"
    assert dusty["score"] > calm["score"]
    assert dusty["factors"][0]["key"] == "dust"
    assert "your normal" in dusty["factors"][0]["detail"]


requires_model = pytest.mark.skipif(not DEFAULT_ARTIFACT.exists(), reason="train the model with `airmate-train` first")


@pytest.fixture(scope="module")
def engine():
    return RiskEngine(explain_samples=24)


@requires_model
def test_trained_model_reacts_to_a_dust_spike(engine):
    assert engine.uses_model
    calm = engine.assess(_history())
    dusty = engine.assess(_history("dust"))
    not_sensitive = engine.assess(_history("dust", triggers=()))
    p = dusty["probabilities"]
    assert p["1h"] <= p["4h"] <= p["12h"]
    assert dusty["score"] >= calm["score"] + 10
    assert dusty["score"] > not_sensitive["score"]
    assert dusty["factors"][0]["key"] == "dust"
    assert dusty["ratios"]["pm10"] > 5
    assert calm["band"] == "low"


@requires_model
def test_explanations_add_up_to_the_score(engine):
    from airmate_ml.features import bin_end_hours, bin_series, build_timeline
    from airmate_ml.schema import OUTDOOR, TRIGGERS

    h = _history("odors", triggers=("odors",))
    n = HISTORY_DAYS * BINS_PER_DAY
    tl = build_timeline(
        bin_series(h.reading_ts, h.readings, h.now, n),
        bin_end_hours(h.now, n, h.utc_offset_seconds),
        np.zeros(n),
        np.zeros(n),
        np.tile([h.outdoor[k] for k in OUTDOOR], (n, 1)),
        np.array([t in h.triggers for t in TRIGGERS], dtype=float),
    )
    seq, ctx = torch.from_numpy(tl.seq[-WINDOW_BINS:][None]), torch.from_numpy(tl.ctx[-1:])
    values, score, normal_day = engine.explainer.explain(seq, ctx)
    assert values.shape == (1, len(engine.explainer.groups))
    assert np.isclose(values.sum(), score[0] - normal_day[0], atol=0.05)
    assert engine.explainer.groups[int(values[0].argmax())] == "odors"


@requires_model
def test_model_handles_missing_sensors(engine):
    only_pm = engine.assess(_history("dust", sensors=("pm",)))
    assert only_pm["sensors_available"] == ["pm"]
    assert only_pm["latest"]["co2"] is None and only_pm["latest"]["pm10"] is not None
    assert 0 <= only_pm["score"] <= 100
    nothing = engine.assess(_history(sensors=()))
    assert nothing["sensors_available"] == [] and 0 <= nothing["score"] <= 100


@requires_model
def test_recent_puffs_raise_risk(engine):
    assert engine.assess(_history(puffs=4))["score"] > engine.assess(_history())["score"]
