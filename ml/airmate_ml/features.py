"""Turn binned sensor readings and logs into model inputs.

The training pipeline (on simulated timelines) and the backend (on the last
week of real readings) both call ``build_timeline``, so the model sees exactly
the same features in both places.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter

from .schema import (
    BIN_SECONDS,
    BINS_PER_DAY,
    BINS_PER_HOUR,
    CTX_FEATURES,
    FFILL_BINS,
    OUTDOOR,
    OUTDOOR_DEFAULTS,
    SENSOR_DEFAULTS,
    SENSOR_GROUPS,
    SENSORS,
    SEQ_FEATURES,
    TRIGGERS,
)

BASELINE_HALF_LIFE_BINS = 24 * BINS_PER_HOUR
BASELINE_PRIOR_BINS = 20.0  # the population default counts as ~1 hour of readings
DEFAULT_COARSE = SENSOR_DEFAULTS["pm10"] - SENSOR_DEFAULTS["pm25"]

SEQ_INDEX = {name: i for i, name in enumerate(SEQ_FEATURES)}
CTX_INDEX = {name: i for i, name in enumerate(CTX_FEATURES)}


@dataclass
class Timeline:
    seq: np.ndarray  # (T, n_seq) float32 model sequence features
    ctx: np.ndarray  # (T, n_ctx) float32 model context features
    raw: np.ndarray  # (T, n_sensors) float32 readings after gap filling / imputation
    masks: dict[str, np.ndarray]  # sensor group -> (T,) bool, True where real data exists
    normal: dict[str, np.ndarray]  # personal baseline in natural units: pm25, coarse, tvoc


def _ffill(values: np.ndarray, valid: np.ndarray, limit: int) -> tuple[np.ndarray, np.ndarray]:
    idx = np.arange(len(valid))
    last = np.maximum.accumulate(np.where(valid, idx, -1))
    ok = (last >= 0) & (idx - last <= limit)
    return values[np.clip(last, 0, None)], ok


def _rolling_sum(x: np.ndarray, window: int) -> np.ndarray:
    """Sum over the trailing ``window`` bins, including the current one."""
    c = np.cumsum(x, axis=0, dtype=np.float64)
    out = c.copy()
    if window < len(c):
        out[window:] -= c[:-window]
    return out


def _masked_rolling_mean(x: np.ndarray, mask: np.ndarray, window: int, default: float) -> np.ndarray:
    m = mask.astype(np.float64)
    s = _rolling_sum(np.where(mask, x, 0.0), window)
    c = _rolling_sum(m, window)
    return np.where(c > 0, s / np.maximum(c, 1.0), default)


def _ewma_valid(x: np.ndarray, valid: np.ndarray, half_life: float, prior: float) -> np.ndarray:
    """Exponentially weighted mean over valid bins only, starting from a decaying prior."""
    a = 1.0 - 0.5 ** (1.0 / half_life)
    num = lfilter([a], [1.0, -(1.0 - a)], np.where(valid, x, 0.0))
    den = lfilter([a], [1.0, -(1.0 - a)], valid.astype(np.float64))
    prior_w = BASELINE_PRIOR_BINS * a * (1.0 - a) ** np.arange(1, len(x) + 1)
    return (num + prior_w * prior) / (den + prior_w)


def build_timeline(
    sensors: np.ndarray,
    hours: np.ndarray,
    puffs: np.ndarray,
    symptoms: np.ndarray,
    outdoor: np.ndarray,
    reported: np.ndarray,
) -> Timeline:
    """Compute per-bin features for one person.

    sensors:  (T, 6) readings in SENSORS order, NaN where missing
    hours:    (T,) local hour of day at the end of each bin
    puffs:    (T,) rescue-inhaler puffs logged in each bin
    symptoms: (T,) symptoms logged in each bin
    outdoor:  (T, 4) forecast in OUTDOOR order (aqi, pollen, temp_c, humidity), NaN allowed
    reported: (6,) self-reported triggers in TRIGGERS order (0/1)
    """
    sensors = np.asarray(sensors, dtype=np.float64)
    n = sensors.shape[0]
    raw = np.empty_like(sensors)
    masks: dict[str, np.ndarray] = {}
    for group, names in SENSOR_GROUPS.items():
        cols = [SENSORS.index(name) for name in names]
        block = sensors[:, cols]
        filled, ok = _ffill(block, np.isfinite(block).all(axis=1), FFILL_BINS)
        defaults = np.array([SENSOR_DEFAULTS[name] for name in names])
        raw[:, cols] = np.where(ok[:, None], filled, defaults)
        masks[group] = ok

    pm25 = np.clip(raw[:, 0], 0.0, None)
    pm10 = np.maximum(raw[:, 1], pm25)
    coarse = pm10 - pm25
    co2 = np.clip(raw[:, 2], 350.0, 10000.0)
    tvoc = np.clip(raw[:, 3], 0.0, None)
    temp = raw[:, 4]
    hum = np.clip(raw[:, 5], 0.0, 100.0)
    log_pm25, log_coarse, log_tvoc = np.log1p(pm25), np.log1p(coarse), np.log1p(tvoc)
    m_pm, m_co2, m_voc, m_cl = masks["pm"], masks["co2"], masks["voc"], masks["climate"]

    base_pm25 = _ewma_valid(log_pm25, m_pm, BASELINE_HALF_LIFE_BINS, np.log1p(SENSOR_DEFAULTS["pm25"]))
    base_coarse = _ewma_valid(log_coarse, m_pm, BASELINE_HALF_LIFE_BINS, np.log1p(DEFAULT_COARSE))
    base_tvoc = _ewma_valid(log_tvoc, m_voc, BASELINE_HALF_LIFE_BINS, np.log1p(SENSOR_DEFAULTS["tvoc"]))

    seq = np.stack(
        [
            log_pm25,
            log_coarse,
            co2 / 1000.0,
            log_tvoc,
            temp,
            hum,
            (log_pm25 - base_pm25) * m_pm,
            (log_coarse - base_coarse) * m_pm,
            (log_tvoc - base_tvoc) * m_voc,
            m_pm,
            m_co2,
            m_voc,
            m_cl,
        ],
        axis=1,
    )

    out = np.asarray(outdoor, dtype=np.float64).reshape(n, len(OUTDOOR))
    out_defaults = np.array([OUTDOOR_DEFAULTS[k] for k in OUTDOOR])
    out = np.where(np.isfinite(out), out, out_defaults)

    puffs = np.asarray(puffs, dtype=np.float64)
    symptoms = np.asarray(symptoms, dtype=np.float64)
    idx = np.arange(n)
    last_puff = np.maximum.accumulate(np.where(puffs > 0, idx, -(10**9)))
    hours_since = np.where(last_puff >= 0, (idx - last_puff) / BINS_PER_HOUR, 72.0)
    six_h, day, week = 6 * BINS_PER_HOUR, BINS_PER_DAY, 7 * BINS_PER_DAY
    angle = 2 * np.pi * np.asarray(hours, dtype=np.float64) / 24.0
    reported = np.asarray(reported, dtype=np.float64).reshape(1, len(TRIGGERS))

    ctx = np.column_stack(
        [
            np.sin(angle),
            np.cos(angle),
            out[:, 0],
            out[:, 1],
            out[:, 2],
            out[:, 3],
            np.log1p(_rolling_sum(puffs, six_h)),
            np.log1p(_rolling_sum(puffs, day)),
            np.log1p(_rolling_sum(puffs, week)),
            np.minimum(hours_since, 72.0) / 72.0,
            np.log1p(_rolling_sum(symptoms, day)),
            np.log1p(_rolling_sum(symptoms, week)),
            _masked_rolling_mean(log_pm25, m_pm, day, np.log1p(SENSOR_DEFAULTS["pm25"])),
            _masked_rolling_mean(log_coarse, m_pm, day, np.log1p(DEFAULT_COARSE)),
            _masked_rolling_mean(log_tvoc, m_voc, day, np.log1p(SENSOR_DEFAULTS["tvoc"])),
            _masked_rolling_mean((hum > 60).astype(np.float64), m_cl, day, 0.0),
            _masked_rolling_mean((co2 > 1000).astype(np.float64), m_co2, day, 0.0),
            _masked_rolling_mean((temp < 18).astype(np.float64), m_cl, day, 0.0),
            _rolling_sum(m_pm.astype(np.float64), day) / day,
            base_pm25,
            base_coarse,
            base_tvoc,
            np.repeat(reported, n, axis=0),
        ]
    )
    assert seq.shape[1] == len(SEQ_FEATURES) and ctx.shape[1] == len(CTX_FEATURES)
    return Timeline(
        seq=seq.astype(np.float32),
        ctx=ctx.astype(np.float32),
        raw=np.column_stack([pm25, pm10, co2, tvoc, temp, hum]).astype(np.float32),
        masks=masks,
        normal={
            "pm25": np.expm1(base_pm25).astype(np.float32),
            "coarse": np.expm1(base_coarse).astype(np.float32),
            "tvoc": np.expm1(base_tvoc).astype(np.float32),
        },
    )


def bin_series(
    ts: np.ndarray, values: np.ndarray, end_ts: float, n_bins: int, reduce: str = "mean"
) -> np.ndarray:
    """Aggregate irregular samples into bins (start, end] that end at ``end_ts``.

    Returns (n_bins, k); empty bins are NaN for ``mean`` and 0 for ``sum``.
    """
    ts = np.asarray(ts, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    if values.ndim == 1:
        values = values[:, None]
    start = end_ts - n_bins * BIN_SECONDS
    idx = np.ceil((ts - start) / BIN_SECONDS).astype(np.int64) - 1
    keep = (idx >= 0) & (idx < n_bins)
    out = np.zeros((n_bins, values.shape[1])) if reduce == "sum" else np.full((n_bins, values.shape[1]), np.nan)
    for j in range(values.shape[1]):
        v, i = values[keep, j], idx[keep]
        ok = np.isfinite(v)
        total = np.bincount(i[ok], weights=v[ok], minlength=n_bins)
        if reduce == "sum":
            out[:, j] = total
        else:
            count = np.bincount(i[ok], minlength=n_bins)
            out[:, j] = np.where(count > 0, total / np.maximum(count, 1), np.nan)
    return out


def bin_end_hours(end_ts: float, n_bins: int, utc_offset_seconds: float) -> np.ndarray:
    """Local hour of day at the end of each bin."""
    ends = end_ts - (n_bins - 1 - np.arange(n_bins)) * BIN_SECONDS
    return ((ends + utc_offset_seconds) / 3600.0) % 24.0
