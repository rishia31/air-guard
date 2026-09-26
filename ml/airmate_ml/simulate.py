"""Synthetic cohort simulator for training and evaluating the Airmate risk model.

No public dataset pairs home air-quality streams with inhaler use, so we
simulate one and say so everywhere the model is described. Each synthetic
person has hidden trigger sensitivities. Indoor air follows a single-zone
mass-balance model driven by cooking, cleaning, candles, sprays, showers,
occupancy, window opening, and outdoor conditions. Flares follow a hazard
process driven by recent exposure (fast attack, slow release), day-scale
airway inflammation, time of day, and rescue-inhaler protection.

The model only ever sees what a real Airmate would see: noisy readings with
missing sensors and offline gaps, outdoor forecasts, logged puffs and
symptoms, and self-reported triggers. The hidden per-trigger hazard
contributions are kept so we can check whether explanations recover the
true cause.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

import numpy as np

from .aqi import pm25_to_aqi
from .schema import BIN_MINUTES, BINS_PER_DAY, BINS_PER_HOUR, SENSOR_GROUPS, SENSORS, TRIGGERS

DT_H = BIN_MINUTES / 60.0
N_TRIG = len(TRIGGERS)

# Log-hazard added per unit of exposure, per trigger (dust, smoke, pollen, humidity, odors, cold air).
ACUTE_WEIGHT = np.array([3.0, 2.4, 1.4, 0.4, 3.2, 1.3])
LATE_WEIGHT = np.array([3.0, 0.4, 2.0, 0.6, 0.2, 0.0])  # allergens also cause a late-phase reaction hours later
CHRONIC_WEIGHT = np.array([0.35, 0.3, 0.6, 0.9, 0.2, 0.3])
TRIGGER_PREVALENCE = np.array([0.22, 0.18, 0.22, 0.12, 0.16, 0.10])
ACUTE_RELEASE = np.exp(-BIN_MINUTES / 90.0)
LATE_KEEP = np.exp(-DT_H / 2.0)
CHRONIC_KEEP = np.exp(-DT_H / 24.0)
INFLAMMATION_KEEP = np.exp(-DT_H / 48.0)
PROTECTION_KEEP = np.exp(-DT_H / 1.5)
BASE_RATE_PER_H = 0.0015
MAX_TRIGGER_LOG_RATE = 8.0  # exposure can raise the flare rate at most ~e^8 (soft cap)
FLARE_INFLAMMATION = 0.35  # each flare leaves the airways more reactive for a couple of days
INFLAMMATION_CAP = 1.2
EXERCISE_PUFF_P = 0.12  # daily chance an exerciser takes a pre-exercise puff (label noise)
# Indoor exposure = log1p(max(level - floor, 0) / scale) for coarse dust (µg/m³), PM2.5 (µg/m³) and TVOC (ppb).
DUST_FLOOR, DUST_SCALE = 15.0, 25.0
SMOKE_FLOOR, SMOKE_SCALE = 35.0, 15.0
VOC_FLOOR, VOC_SCALE = 300.0, 150.0
STUFFY_WEIGHT = 0.4  # log-hazard per 800 ppm of CO2 above 1200 (poor ventilation, not a trigger by itself)
WINDOW_ACH = 4.0
SENSOR_PRESENCE = {"pm": 0.97, "co2": 0.8, "voc": 0.75, "climate": 0.92}


@dataclass
class Cohort:
    sensors: np.ndarray  # (U, T, 6) float32 readings, NaN where missing
    outdoor: np.ndarray  # (U, T, 4) float32 forecast: aqi, pollen, temp_c, humidity
    puffs: np.ndarray  # (U, T) int16 logged rescue-inhaler puffs
    symptoms: np.ndarray  # (U, T) int16 logged symptoms
    hour: np.ndarray  # (T,) float32 local hour at the end of each bin
    reported: np.ndarray  # (U, 6) float32 self-reported triggers
    sensitivity: np.ndarray  # (U, 6) float32 hidden true sensitivities
    flares: np.ndarray  # (U, T) bool hidden true flares
    contrib: np.ndarray  # (U, T, 6) float16 hidden per-trigger log-hazard contribution
    log_rate: np.ndarray  # (U, T) float32 hidden true log flare rate per hour

    @property
    def n_users(self) -> int:
        return self.sensors.shape[0]

    @property
    def n_bins(self) -> int:
        return self.sensors.shape[1]

    @staticmethod
    def concat(parts: list[Cohort]) -> Cohort:
        kwargs = {}
        for f in fields(Cohort):
            if f.name == "hour":
                kwargs[f.name] = parts[0].hour
            else:
                kwargs[f.name] = np.concatenate([getattr(p, f.name) for p in parts], axis=0)
        return Cohort(**kwargs)


def simulate_cohort(n_users: int, days: int = 14, seed: int = 0, chunk: int = 128) -> Cohort:
    """Simulate ``n_users`` people for ``days`` days at 3-minute resolution."""
    rng = np.random.default_rng(seed)
    parts = []
    for start in range(0, n_users, chunk):
        n = min(chunk, n_users - start)
        sub = np.random.default_rng(int(rng.integers(0, 2**63 - 1)))
        parts.append(simulate_people(sub, sample_people(sub, n), days))
    return Cohort.concat(parts)


def _bump(x: np.ndarray, center: float, width: float) -> np.ndarray:
    return np.exp(-0.5 * ((x - center) / width) ** 2)


def sample_people(rng: np.random.Generator, n: int) -> dict[str, np.ndarray]:
    sens = rng.uniform(0.0, 0.25, size=(n, N_TRIG))
    n_major = rng.choice([1, 2, 3], size=n, p=[0.35, 0.4, 0.25])
    for i in range(n):
        major = rng.choice(N_TRIG, size=n_major[i], replace=False, p=TRIGGER_PREVALENCE)
        sens[i, major] = rng.uniform(0.8, 1.6, size=n_major[i])
    strong = sens > 0.6
    reported = np.where(strong, rng.random((n, N_TRIG)) < 0.85, rng.random((n, N_TRIG)) < 0.08)
    bedroom = rng.random(n) < 0.6
    return {
        "sens": sens,
        "reported": reported.astype(np.float32),
        "base_log_rate": np.log(BASE_RATE_PER_H) + rng.normal(0, 0.35, n) + 0.5 * (rng.random(n) < 0.3),
        "vent": np.clip(np.exp(rng.normal(np.log(0.5), 0.4, n)), 0.15, 1.5),
        "window_habit": rng.random(n),
        "bedroom": bedroom,
        "volume": np.where(bedroom, rng.uniform(25, 40, n), rng.uniform(55, 90, n)),
        "occupants": rng.choice([1, 2, 3, 4], size=n, p=[0.3, 0.35, 0.2, 0.15]),
        "works_away": rng.random(n) < 0.7,
        "stove": rng.uniform(0.4, 2.0, n),
        "gas": rng.random(n) < 0.35,
        "clean_rate": rng.uniform(0.1, 0.45, n),
        "dusty_rate": rng.uniform(0.0, 0.12, n),
        "candle_rate": rng.uniform(0.0, 0.3, n) * (rng.random(n) < 0.5),
        "spray_rate": rng.uniform(0.0, 0.25, n),
        "pet_coarse": np.where(rng.random(n) < 0.4, rng.uniform(4, 14, n), 0.0),
        "hum_base": np.where(rng.random(n) < 0.2, rng.uniform(60, 70, n), rng.uniform(35, 55, n)),
        "setpoint": rng.uniform(20, 24, n),
        "cold_home": rng.random(n) < 0.12,
        "has_ac": rng.random(n) < 0.8,
        "bg_voc": rng.uniform(60, 250, n),
        "exercise": rng.random(n) < 0.3,
        "start_doy": rng.integers(0, 365, n),
        "start_dow": rng.integers(0, 7, n),
        "presence": {g: rng.random(n) < p for g, p in SENSOR_PRESENCE.items()},
    }


def _outdoor(rng: np.random.Generator, p: dict, n_days: int) -> dict[str, np.ndarray]:
    n = len(p["vent"])
    doy = (p["start_doy"][:, None] + np.arange(n_days)[None, :]) % 365
    season = np.cos(2 * np.pi * (doy - 200) / 365)  # +1 in mid-July, -1 in mid-January
    rain = rng.random((n, n_days)) < 0.25
    pollen = 4.5 * _bump(doy, 95, 18) + 2.2 * _bump(doy, 150, 25) + 3.0 * _bump(doy, 255, 20)
    pollen = np.clip(np.where(rain, 0.4, 1.0) * (pollen + 0.4 + rng.normal(0, 0.5, (n, n_days))), 0, 5)
    smoke = np.zeros((n, n_days), bool)
    for d in range(n_days):
        prev = smoke[:, d - 1] if d else np.zeros(n, bool)
        smoke[:, d] = np.where(prev, rng.random(n) < 0.6, rng.random(n) < 0.015)
    pm25_day = np.exp(rng.normal(np.log(7), 0.35, (n, n_days))) + smoke * rng.uniform(20, 70, (n, n_days))
    temp_day = 17 + 10 * season + rng.normal(0, 2.5, (n, n_days))
    rh_day = np.clip(62 + 8 * season + rng.normal(0, 6, (n, n_days)) + 15 * rain, 25, 95)

    n_bins = n_days * BINS_PER_DAY
    hours = ((np.arange(n_bins) % BINS_PER_DAY) + 1) / BINS_PER_HOUR % 24
    day = np.arange(n_bins) // BINS_PER_DAY
    diurnal = np.cos(2 * np.pi * (hours - 15) / 24)
    return {
        "season": season,
        "temp_day": temp_day,
        "hours": hours,
        "day": day,
        "pollen": pollen[:, day],
        "pm25": pm25_day[:, day] * (1 + 0.2 * np.cos(2 * np.pi * (hours - 8) / 12)),
        "coarse": rng.uniform(6, 20, (n, n_days))[:, day],
        "temp": temp_day[:, day] + 5 * diurnal,
        "rh": np.clip(rh_day[:, day] - 12 * diurnal, 15, 100),
        "aqi_fc": (pm25_to_aqi(pm25_day) * np.exp(rng.normal(0, 0.12, (n, n_days))))[:, day],
        "pollen_fc": np.clip(pollen + rng.normal(0, 0.4, (n, n_days)), 0, 5)[:, day],
    }


def _schedule(rng: np.random.Generator, p: dict, out: dict, n_days: int) -> dict[str, np.ndarray]:
    n = len(p["vent"])
    n_bins = n_days * BINS_PER_DAY
    home = np.ones((n, n_bins), bool)
    asleep = np.zeros((n, n_bins), bool)
    window = np.zeros((n, n_bins), bool)
    acts = {k: np.zeros((n, n_bins), np.float32) for k in ("cook", "clean", "dusty", "candle", "spray", "shower")}
    exercise_puff = np.zeros((n, n_bins), np.int16)

    def span(arr: np.ndarray, i: int, day: int, start_h: float, dur_h: float, value=1) -> None:
        a = int(day * BINS_PER_DAY + start_h * BINS_PER_HOUR)
        b = a + max(1, int(round(dur_h * BINS_PER_HOUR)))
        arr[i, max(a, 0) : min(b, n_bins)] = value

    for i in range(n):
        for d in range(n_days):
            weekday = (p["start_dow"][i] + d) % 7 < 5
            wake, sleep = rng.normal(7.0, 0.6), rng.normal(23.0, 0.6)
            span(asleep, i, d, 0, wake, True)
            span(asleep, i, d, sleep, 24 - sleep, True)
            if p["works_away"][i] and weekday:
                leave, back = rng.normal(8.4, 0.4), rng.normal(17.6, 0.8)
                span(home, i, d, leave, back - leave, False)
            elif rng.random() < 0.6:
                span(home, i, d, rng.uniform(10, 16), rng.uniform(1.5, 4), False)
            comfy = 14 <= out["temp_day"][i, d] <= 26
            if rng.random() < p["window_habit"][i] * (0.85 if comfy else 0.12):
                span(window, i, d, rng.uniform(9, 14), rng.uniform(2, 9), True)
            if rng.random() < 0.45:
                span(acts["cook"], i, d, wake + 0.4, 0.33)
            if rng.random() < 0.8:
                span(acts["cook"], i, d, rng.uniform(17.8, 19.6), rng.uniform(0.5, 0.85))
            for _ in range(rng.poisson(p["clean_rate"][i])):
                span(acts["clean"], i, d, rng.uniform(9, 20), rng.uniform(0.3, 0.6))
            for _ in range(rng.poisson(p["dusty_rate"][i])):
                span(acts["dusty"], i, d, rng.uniform(9, 20), rng.uniform(0.1, 0.25))
            for _ in range(rng.poisson(p["candle_rate"][i])):
                span(acts["candle"], i, d, rng.uniform(18.5, 21.5), rng.uniform(1, 2))
            for _ in range(rng.poisson(p["spray_rate"][i])):
                span(acts["spray"], i, d, rng.uniform(9, 21), rng.uniform(0.1, 0.15))
            if rng.random() < 0.8:
                span(acts["shower"], i, d, wake + 0.2, 0.25)
            if p["exercise"][i] and rng.random() < EXERCISE_PUFF_P:
                exercise_puff[i, int(d * BINS_PER_DAY + rng.uniform(7, 20) * BINS_PER_HOUR)] = 2

    awake_home = home & ~asleep
    for arr in acts.values():
        arr *= awake_home
    return {"home": home, "asleep": asleep, "window": window & ~asleep, "exercise_puff": exercise_puff, **acts}


def simulate_people(
    rng: np.random.Generator,
    p: dict,
    days: int,
    schedule_hook=None,
) -> Cohort:
    """Run the simulation for the people in ``p``.

    ``schedule_hook(schedule, outdoor)`` may edit the activity schedule in place
    (used to script the demo patient's week). One burn-in day is simulated and
    dropped so inflammation and baselines start near steady state.
    """
    n = len(p["vent"])
    n_days = days + 1
    n_bins = n_days * BINS_PER_DAY
    out = _outdoor(rng, p, n_days)
    s = _schedule(rng, p, out, n_days)
    if schedule_hook is not None:
        schedule_hook(s, out)

    sens = p["sens"]
    in_bedroom = p["bedroom"]
    winter = out["season"][:, out["day"]] < -0.3
    summer = out["season"][:, out["day"]] > 0.4
    hum_target_base = (
        p["hum_base"][:, None]
        + np.where(summer & ~p["has_ac"][:, None], 8.0, 0.0)
        - np.where(summer & p["has_ac"][:, None], 4.0, 0.0)
        - np.where(winter, 8.0, 0.0)
    )
    setpoint = np.where(p["cold_home"][:, None] & winter, 16.5, p["setpoint"][:, None])

    pm25 = np.full(n, 6.0)
    coarse = np.full(n, 8.0)
    co2 = np.full(n, 600.0)
    tvoc = p["bg_voc"].copy()
    temp = p["setpoint"].copy()
    rh = p["hum_base"].copy()
    acute = np.zeros((n, N_TRIG))
    late_1 = np.zeros((n, N_TRIG))
    late_2 = np.zeros((n, N_TRIG))
    chronic = np.zeros((n, N_TRIG))
    inflammation = np.zeros(n)
    protection = np.zeros(n)

    true = np.zeros((n, n_bins, len(SENSORS)), np.float32)
    puffs = np.zeros((n, n_bins), np.int16)
    symptoms = np.zeros((n, n_bins), np.int16)
    flares = np.zeros((n, n_bins), bool)
    contrib = np.zeros((n, n_bins, N_TRIG), np.float16)
    true_log_rate = np.zeros((n, n_bins), np.float32)
    puff_choices = np.array([1, 2, 3, 4])

    for t in range(n_bins):
        home, asleep, win = s["home"][:, t], s["asleep"][:, t], s["window"][:, t]
        cook, clean, dusty = s["cook"][:, t], s["clean"][:, t], s["dusty"][:, t]
        candle, spray, shower = s["candle"][:, t], s["spray"][:, t], s["shower"][:, t]
        awake_home = home & ~asleep
        ach = p["vent"] + WINDOW_ACH * win

        k = ach + 0.25
        eq = (0.8 * ach * out["pm25"][:, t] + 160 * p["stove"] * cook + 70 * candle + 60 * dusty + 25 * clean) / k
        pm25 = eq + (pm25 - eq) * np.exp(-k * DT_H)

        k = ach + 1.6
        src = 650 * clean + 3000 * dusty + awake_home * (6 + p["pet_coarse"]) + 30 * cook
        eq = (0.5 * ach * out["coarse"][:, t] + src) / k
        coarse = eq + (coarse - eq) * np.exp(-k * DT_H)

        people = np.where(
            in_bedroom,
            np.where(asleep & home, np.minimum(p["occupants"], 2), 0.3 * awake_home),
            np.where(awake_home, 0.8 * p["occupants"], 0.0),
        )
        gen = people * np.where(asleep, 0.013, 0.018) + 0.02 * cook * p["gas"]
        eq = 420 + gen * 1e6 / (ach * p["volume"])
        co2 = eq + (co2 - eq) * np.exp(-ach * DT_H)

        k = ach + 0.5
        eq = (0.9 * p["bg_voc"] + 500 * cook + 800 * candle + 12000 * spray + 400 * clean) / k
        tvoc = eq + (tvoc - eq) * np.exp(-k * DT_H)

        mix = 0.65 * win
        t_target = (1 - mix) * (setpoint[:, t] - 1.5 * asleep) + mix * out["temp"][:, t]
        temp = t_target + (temp - t_target) * np.exp(-DT_H) + 0.4 * cook
        rh_target = (1 - mix) * hum_target_base[:, t] + mix * out["rh"][:, t]
        rh = rh_target + (rh - rh_target) * np.exp(-1.3 * DT_H) + shower * np.where(in_bedroom, 6.0, 2.0) + 1.5 * cook
        rh = np.clip(rh, 12, 98)

        true[:, t] = np.stack([pm25, pm25 + coarse, co2, tvoc, temp, rh], axis=1)

        exposure_home = np.stack(
            [
                np.log1p(np.maximum(coarse - DUST_FLOOR, 0) / DUST_SCALE),
                np.log1p(np.maximum(pm25 - SMOKE_FLOOR, 0) / SMOKE_SCALE),
                out["pollen"][:, t] / 2 * (0.08 + 0.55 * win),
                np.maximum(0.0, (rh - 55) / 15),
                np.log1p(np.maximum(tvoc - VOC_FLOOR, 0) / VOC_SCALE),
                np.maximum(0.0, (18 - temp) / 2.5),
            ],
            axis=1,
        )
        pm_away = 0.8 * out["pm25"][:, t] + 3
        exposure_away = np.stack(
            [
                np.full(n, 0.2),
                np.log1p(np.maximum(pm_away - 10, 0) / 15),
                out["pollen"][:, t] / 2 * 0.6,
                np.zeros(n),
                np.full(n, 0.2),
                0.3 * np.maximum(0.0, (10 - out["temp"][:, t]) / 6),
            ],
            axis=1,
        )
        exposure = np.where(home[:, None], exposure_home, exposure_away)
        stuffy = np.maximum(0.0, (co2 - 1200) / 800) * home

        acute = np.maximum(exposure, acute * ACUTE_RELEASE)
        late_1 = late_1 * LATE_KEEP + (1 - LATE_KEEP) * acute
        late_2 = late_2 * LATE_KEEP + (1 - LATE_KEEP) * late_1
        chronic = chronic * CHRONIC_KEEP + (1 - CHRONIC_KEEP) * exposure
        per_trigger = sens * (ACUTE_WEIGHT * acute + LATE_WEIGHT * late_2 + CHRONIC_WEIGHT * chronic)
        trigger_total = MAX_TRIGGER_LOG_RATE * np.tanh(per_trigger.sum(axis=1) / MAX_TRIGGER_LOG_RATE)
        circadian = 0.35 * np.cos(2 * np.pi * (out["hours"][t] - 4) / 24)
        log_rate = (
            p["base_log_rate"]
            + circadian
            + trigger_total
            + STUFFY_WEIGHT * stuffy
            + 0.8 * inflammation
            - 1.6 * protection
        )
        rate = np.exp(log_rate)
        flare = rng.random(n) < 1 - np.exp(-rate * DT_H)
        logged = flare & (rng.random(n) < 0.92)
        n_puffs = rng.choice(puff_choices, size=n, p=[0.2, 0.6, 0.1, 0.1])
        puffs[:, t] = np.where(logged, n_puffs, 0) + s["exercise_puff"][:, t]
        precursor = rng.random(n) < 1 - np.exp(-0.25 * rate * DT_H)
        symptoms[:, t] = (flare & (rng.random(n) < 0.5)) | precursor
        protection = np.minimum(protection * PROTECTION_KEEP + (puffs[:, t] > 0), 1.5)
        inflammation = np.minimum(inflammation * INFLAMMATION_KEEP + FLARE_INFLAMMATION * flare, INFLAMMATION_CAP)
        flares[:, t] = flare
        contrib[:, t] = per_trigger
        true_log_rate[:, t] = log_rate

    keep = slice(BINS_PER_DAY, None)
    readings = _measure(rng, p, true[:, keep])
    outdoor = np.stack(
        [
            out["aqi_fc"][:, keep],
            out["pollen_fc"][:, keep],
            out["temp"][:, keep] + rng.normal(0, 1.0, out["temp"][:, keep].shape),
            out["rh"][:, keep] + rng.normal(0, 4.0, out["rh"][:, keep].shape),
        ],
        axis=-1,
    ).astype(np.float32)
    return Cohort(
        sensors=readings,
        outdoor=outdoor,
        puffs=puffs[:, keep],
        symptoms=symptoms[:, keep],
        hour=out["hours"][keep].astype(np.float32),
        reported=p["reported"],
        sensitivity=sens.astype(np.float32),
        flares=flares[:, keep],
        contrib=contrib[:, keep],
        log_rate=true_log_rate[:, keep],
    )


def _measure(rng: np.random.Generator, p: dict, true: np.ndarray) -> np.ndarray:
    """Add sensor noise, missing sensors, and offline gaps."""
    n, n_bins, _ = true.shape
    pm25 = np.clip(true[..., 0] * (1 + rng.normal(0, 0.08, (n, n_bins))) + rng.normal(0, 1.0, (n, n_bins)), 0, None)
    coarse = np.clip((true[..., 1] - true[..., 0]) * (1 + rng.normal(0, 0.12, (n, n_bins))), 0, None)
    readings = np.stack(
        [
            pm25,
            pm25 + coarse,
            true[..., 2] + rng.normal(0, 30, (n, n_bins)),
            np.clip(true[..., 3] * (1 + rng.normal(0, 0.15, (n, n_bins))), 0, None),
            true[..., 4] + rng.normal(0, 0.2, (n, n_bins)),
            np.clip(true[..., 5] + rng.normal(0, 1.5, (n, n_bins)), 0, 100),
        ],
        axis=-1,
    ).astype(np.float32)
    for group, names in SENSOR_GROUPS.items():
        cols = [SENSORS.index(name) for name in names]
        absent = ~p["presence"][group]
        readings[np.ix_(absent, np.arange(n_bins), cols)] = np.nan
    for i in range(n):
        for _ in range(rng.poisson(1.5)):
            start = rng.integers(0, n_bins)
            readings[i, start : start + int(rng.uniform(0.5, 8) * BINS_PER_HOUR)] = np.nan
    return readings
