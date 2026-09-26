import numpy as np
from airmate_ml.aqi import category, pm25_to_aqi
from airmate_ml.features import CTX_INDEX, SEQ_INDEX, bin_end_hours, bin_series, build_timeline
from airmate_ml.schema import BIN_SECONDS, BINS_PER_DAY, BINS_PER_HOUR, CTX_FEATURES, SENSORS, SEQ_FEATURES


def _steady(n: int, pm25=6.0, pm10=14.0, co2=650.0, tvoc=120.0, temp=22.0, rh=45.0) -> np.ndarray:
    return np.tile(np.array([pm25, pm10, co2, tvoc, temp, rh], dtype=np.float64), (n, 1))


def _timeline(sensors, puffs=None, symptoms=None, reported=None):
    n = len(sensors)
    return build_timeline(
        sensors,
        (np.arange(n) / BINS_PER_HOUR) % 24,
        np.zeros(n) if puffs is None else puffs,
        np.zeros(n) if symptoms is None else symptoms,
        np.tile([40.0, 1.5, 20.0, 55.0], (n, 1)),
        np.zeros(6) if reported is None else reported,
    )


def test_aqi_breakpoints():
    assert pm25_to_aqi(0.0) == 0
    assert pm25_to_aqi(9.0) == 50
    assert pm25_to_aqi(35.4) == 100
    assert round(float(pm25_to_aqi(55.4))) == 150
    assert category(42)[0] == "Good"
    assert category(120)[0].startswith("Unhealthy for sensitive")


def test_bin_series_is_right_closed_and_aggregates():
    end = 1_000_000.0
    ts = np.array([end, end - 1, end - BIN_SECONDS, end - BIN_SECONDS - 1, end - 10 * BIN_SECONDS, end + 5])
    vals = np.array([1.0, 3.0, 5.0, 7.0, 9.0, 100.0])
    mean = bin_series(ts, vals, end, 10)
    assert mean.shape == (10, 1)
    assert mean[-1, 0] == 2.0  # (end - 180, end] holds the first two samples
    assert mean[-2, 0] == 6.0
    assert np.isnan(mean[0, 0])  # the sample at exactly end - 10 bins is outside the window
    total = bin_series(ts, vals, end, 10, reduce="sum")
    assert total[-1, 0] == 4.0 and total[0, 0] == 0.0


def test_bin_end_hours_uses_local_offset():
    end = 12 * 3600.0  # 12:00 UTC
    hours = bin_end_hours(end, 3, utc_offset_seconds=-4 * 3600)
    assert np.allclose(hours, [8.0 - 2 * BIN_SECONDS / 3600, 8.0 - BIN_SECONDS / 3600, 8.0])


def test_timeline_shapes_and_steady_state_baseline():
    n = 3 * BINS_PER_DAY
    tl = _timeline(_steady(n))
    assert tl.seq.shape == (n, len(SEQ_FEATURES)) and tl.ctx.shape == (n, len(CTX_FEATURES))
    assert tl.seq.dtype == np.float32
    assert all(m.all() for m in tl.masks.values())
    # With constant air the personal baseline converges to the readings and relative features vanish.
    assert abs(tl.normal["pm25"][-1] - 6.0) < 0.1
    assert abs(tl.normal["coarse"][-1] - 8.0) < 0.1
    assert np.abs(tl.seq[-1, [SEQ_INDEX["rel_pm25"], SEQ_INDEX["rel_coarse"], SEQ_INDEX["rel_tvoc"]]]).max() < 0.02


def test_spike_is_relative_to_personal_baseline():
    n = 2 * BINS_PER_DAY
    sensors = _steady(n)
    sensors[-10:, 1] = 120.0  # dust spike: PM10 jumps, PM2.5 unchanged
    tl = _timeline(sensors)
    assert tl.seq[-1, SEQ_INDEX["rel_coarse"]] > 2.0
    assert abs(tl.seq[-1, SEQ_INDEX["rel_pm25"]]) < 0.05


def test_missing_sensors_are_masked_and_gaps_forward_filled():
    n = 200
    sensors = _steady(n)
    sensors[:, 3] = np.nan  # no VOC sensor at all
    sensors[100:103, 0:2] = np.nan  # short PM dropout: forward-filled
    sensors[150:170, 4:6] = np.nan  # long climate dropout: masked after FFILL_BINS
    tl = _timeline(sensors)
    assert not tl.masks["voc"].any()
    assert tl.seq[:, SEQ_INDEX["has_voc"]].max() == 0
    assert tl.seq[:, SEQ_INDEX["rel_tvoc"]].max() == 0
    assert tl.masks["pm"][100:103].all()
    assert tl.masks["climate"][150:155].all() and not tl.masks["climate"][156:170].any()
    assert np.isfinite(tl.seq).all() and np.isfinite(tl.ctx).all()


def test_pm10_is_never_below_pm25():
    sensors = _steady(50, pm25=30.0, pm10=20.0)
    tl = _timeline(sensors)
    assert (tl.raw[:, SENSORS.index("pm10")] >= tl.raw[:, SENSORS.index("pm25")]).all()
    assert tl.seq[-1, SEQ_INDEX["log_coarse"]] == 0


def test_inhaler_and_symptom_history():
    n = 2 * BINS_PER_DAY
    puffs = np.zeros(n)
    puffs[n - 1 - 2 * BINS_PER_HOUR] = 2  # two puffs two hours before the last bin
    puffs[n - 1 - 30 * BINS_PER_HOUR] = 1  # one puff 30 hours before
    symptoms = np.zeros(n)
    symptoms[-5] = 1
    tl = _timeline(_steady(n), puffs=puffs, symptoms=symptoms, reported=np.array([1, 0, 0, 0, 0, 0]))
    last = tl.ctx[-1]
    assert np.isclose(np.expm1(last[CTX_INDEX["puffs_6h"]]), 2)
    assert np.isclose(np.expm1(last[CTX_INDEX["puffs_24h"]]), 2)
    assert np.isclose(np.expm1(last[CTX_INDEX["puffs_7d"]]), 3)
    assert np.isclose(last[CTX_INDEX["hours_since_puff"]] * 72, 2.0)
    assert np.isclose(np.expm1(last[CTX_INDEX["symptoms_24h"]]), 1)
    assert last[CTX_INDEX["trig_dust"]] == 1 and last[CTX_INDEX["trig_pollen"]] == 0
