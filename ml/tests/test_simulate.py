import numpy as np
import pytest

from airmate_ml.data import build_dataset, split_users
from airmate_ml.schema import BINS_PER_DAY, SENSORS, TRIGGERS, WINDOW_BINS
from airmate_ml.simulate import sample_people, simulate_cohort, simulate_people


@pytest.fixture(scope="module")
def cohort():
    return simulate_cohort(24, days=4, seed=3)


def test_cohort_shapes(cohort):
    assert cohort.sensors.shape == (24, 4 * BINS_PER_DAY, len(SENSORS))
    assert cohort.outdoor.shape == (24, 4 * BINS_PER_DAY, 4)
    assert cohort.contrib.shape == (24, 4 * BINS_PER_DAY, len(TRIGGERS))
    assert cohort.hour.shape == (4 * BINS_PER_DAY,)
    assert cohort.reported.shape == cohort.sensitivity.shape == (24, len(TRIGGERS))


def test_readings_are_physical(cohort):
    s = cohort.sensors
    pm25, pm10, co2, tvoc, temp, rh = (s[..., i] for i in range(6))
    assert np.nanmin(pm25) >= 0 and np.nanmin(tvoc) >= 0
    assert np.nanmin(pm10 - pm25) >= 0
    assert 350 < np.nanmedian(co2) < 1500
    assert 14 < np.nanmedian(temp) < 28
    assert 0 <= np.nanmin(rh) and np.nanmax(rh) <= 100
    assert np.isnan(s).any()  # offline gaps and missing sensors exist


def test_flare_rate_is_plausible(cohort):
    per_week = cohort.flares.sum(axis=1) / 4 * 7
    assert 0.2 < per_week.mean() < 6
    assert (cohort.puffs >= 0).all()
    assert cohort.puffs[cohort.flares].mean() > 1  # most flares are logged with 1-4 puffs


def test_simulation_is_deterministic():
    a = simulate_cohort(4, days=2, seed=11)
    b = simulate_cohort(4, days=2, seed=11)
    assert np.array_equal(a.puffs, b.puffs)
    assert np.allclose(np.nan_to_num(a.sensors), np.nan_to_num(b.sensors))


def test_schedule_hook_scripts_activities():
    rng = np.random.default_rng(0)
    people = sample_people(rng, 1)
    people["sens"][:] = [1.5, 0, 0, 0, 0, 0]
    people["presence"] = {g: np.array([True]) for g in people["presence"]}

    def hook(schedule, outdoor):
        for key in ("clean", "dusty", "cook", "candle", "spray"):
            schedule[key][:] = 0
        schedule["home"][:] = True
        day2 = BINS_PER_DAY * 2 + 15 * 20  # 15:00 on the second simulated day (after burn-in)
        schedule["dusty"][0, day2 : day2 + 6] = 1.0

    c = simulate_people(rng, people, days=2, schedule_hook=hook)
    coarse = c.sensors[0, :, 1] - c.sensors[0, :, 0]
    spike_at = BINS_PER_DAY + 15 * 20 + 5
    assert np.nanmax(coarse[spike_at - 3 : spike_at + 3]) > 5 * np.nanmedian(coarse[: BINS_PER_DAY // 2])
    assert c.contrib[0, spike_at, 0] > c.contrib[0, spike_at - 60, 0]


def test_dataset_windows_and_user_split(cohort):
    data = build_dataset(cohort)
    train, val, test = split_users(cohort.n_users, seed=0)
    assert not set(train) & set(test) and not set(val) & set(test)
    idx = data.indices(test, stride=7)
    seq, ctx = data.windows(idx)
    assert seq.shape == (len(idx), WINDOW_BINS, data.seq.shape[1])
    assert np.isfinite(seq).all() and np.isfinite(ctx).all()
    assert (data.local_t[idx] >= WINDOW_BINS - 1).all()
    # Each window stays within a single person's timeline.
    starts = idx - WINDOW_BINS + 1
    assert (data.user[starts] == data.user[idx]).all()
