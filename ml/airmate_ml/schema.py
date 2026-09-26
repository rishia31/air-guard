"""Feature, label, and explanation definitions shared by simulation, training, and serving.

Keeping these in one place is what prevents train/serve skew: the simulator,
the training pipeline, and the backend all build model inputs through
``features.build_timeline`` using the names and constants below.
"""

from __future__ import annotations

BIN_MINUTES = 3
BIN_SECONDS = BIN_MINUTES * 60
BINS_PER_HOUR = 60 // BIN_MINUTES
BINS_PER_DAY = 24 * BINS_PER_HOUR
WINDOW_BINS = 3 * BINS_PER_HOUR  # the GRU sees the last 3 hours at 3-minute resolution
HISTORY_DAYS = 7  # serving needs a week of history for baselines and 7-day counts
FFILL_BINS = 5  # carry a reading forward for up to 15 minutes before calling it missing

# Discrete-time survival head: conditional hazard for each interval (hours).
HORIZON_HOURS = (1, 4, 12)
SCORE_HORIZON_INDEX = 1  # the 0-100 risk score is P(rescue inhaler needed within 4 h)
BAND_THRESHOLDS = (20, 45)  # score < 20 low, < 45 elevated, otherwise high

SENSORS = ("pm25", "pm10", "co2", "tvoc", "temp_c", "humidity")
SENSOR_UNITS = {"pm25": "µg/m³", "pm10": "µg/m³", "co2": "ppm", "tvoc": "ppb", "temp_c": "°C", "humidity": "%"}
SENSOR_GROUPS = {
    "pm": ("pm25", "pm10"),
    "co2": ("co2",),
    "voc": ("tvoc",),
    "climate": ("temp_c", "humidity"),
}
SENSOR_DEFAULTS = {"pm25": 8.0, "pm10": 12.0, "co2": 600.0, "tvoc": 150.0, "temp_c": 22.0, "humidity": 45.0}

OUTDOOR = ("aqi", "pollen", "temp_c", "humidity")
OUTDOOR_DEFAULTS = {"aqi": 40.0, "pollen": 1.5, "temp_c": 20.0, "humidity": 55.0}

TRIGGERS = ("dust", "smoke", "pollen", "humidity", "odors", "cold_air")
TRIGGER_LABELS = {
    "dust": "Dust",
    "smoke": "Smoke & fine particles",
    "pollen": "Pollen",
    "humidity": "Humidity & mold",
    "odors": "Strong odors & chemicals",
    "cold_air": "Cold air",
}

SEQ_FEATURES = (
    "log_pm25",
    "log_coarse",
    "co2_k",
    "log_tvoc",
    "temp_c",
    "humidity",
    "rel_pm25",
    "rel_coarse",
    "rel_tvoc",
    "has_pm",
    "has_co2",
    "has_voc",
    "has_climate",
)

CTX_FEATURES = (
    "hour_sin",
    "hour_cos",
    "aqi",
    "pollen",
    "outdoor_temp_c",
    "outdoor_humidity",
    "puffs_6h",
    "puffs_24h",
    "puffs_7d",
    "hours_since_puff",
    "symptoms_24h",
    "symptoms_7d",
    "mean_log_pm25_24h",
    "mean_log_coarse_24h",
    "mean_log_tvoc_24h",
    "frac_humid_24h",
    "frac_stuffy_24h",
    "frac_cold_24h",
    "pm_coverage_24h",
    "base_log_pm25",
    "base_log_coarse",
    "base_log_tvoc",
    *(f"trig_{t}" for t in TRIGGERS),
)

# Feature groups used for Shapley explanations. Each group is swapped for a
# "normal day" reference (see explain.py) to measure how many risk points it adds.
EXPLAIN_GROUPS = {
    "dust": {"seq": ("log_coarse", "rel_coarse"), "ctx": ("mean_log_coarse_24h",)},
    "smoke": {"seq": ("log_pm25", "rel_pm25"), "ctx": ("mean_log_pm25_24h",)},
    "odors": {"seq": ("log_tvoc", "rel_tvoc"), "ctx": ("mean_log_tvoc_24h",)},
    "stuffy_air": {"seq": ("co2_k",), "ctx": ("frac_stuffy_24h",)},
    "humidity": {"seq": ("humidity",), "ctx": ("frac_humid_24h",)},
    "cold_air": {"seq": ("temp_c",), "ctx": ("frac_cold_24h",)},
    "pollen": {"seq": (), "ctx": ("pollen",)},
    "outdoor_air": {"seq": (), "ctx": ("aqi",)},
    "weather": {"seq": (), "ctx": ("outdoor_temp_c", "outdoor_humidity")},
    "inhaler_use": {"seq": (), "ctx": ("puffs_6h", "puffs_24h", "puffs_7d", "hours_since_puff")},
    "symptoms": {"seq": (), "ctx": ("symptoms_24h", "symptoms_7d")},
    "time_of_day": {"seq": (), "ctx": ("hour_sin", "hour_cos")},
}

GROUP_LABELS = {
    "dust": "Dust",
    "smoke": "Smoke & fine particles",
    "odors": "Odors & chemicals (VOCs)",
    "stuffy_air": "Stuffy air (CO₂)",
    "humidity": "Humidity",
    "cold_air": "Cold indoor air",
    "pollen": "Pollen forecast",
    "outdoor_air": "Outdoor air quality",
    "weather": "Outdoor weather",
    "inhaler_use": "Recent inhaler use",
    "symptoms": "Recent symptoms",
    "time_of_day": "Time of day",
}

# Which simulated trigger each explanation group corresponds to (for evaluation).
GROUP_TO_TRIGGER = {
    "dust": "dust",
    "smoke": "smoke",
    "odors": "odors",
    "humidity": "humidity",
    "cold_air": "cold_air",
    "weather": "cold_air",
    "pollen": "pollen",
}


def band_for(score: float) -> str:
    low, high = BAND_THRESHOLDS
    if score < low:
        return "low"
    if score < high:
        return "elevated"
    return "high"
