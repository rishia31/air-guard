"""US EPA Air Quality Index helpers (PM2.5 breakpoints from the 2024 NAAQS update)."""

from __future__ import annotations

import numpy as np

_PM25_C = [0.0, 9.0, 9.1, 35.4, 35.5, 55.4, 55.5, 125.4, 125.5, 225.4, 225.5, 325.4]
_PM25_I = [0, 50, 51, 100, 101, 150, 151, 200, 201, 300, 301, 500]
_PM10_C = [0, 54, 55, 154, 155, 254, 255, 354, 355, 424, 425, 604]
_PM10_I = [0, 50, 51, 100, 101, 150, 151, 200, 201, 300, 301, 500]

CATEGORIES = (
    (50, "Good", "#10b981"),
    (100, "Moderate", "#eab308"),
    (150, "Unhealthy for sensitive groups", "#f97316"),
    (200, "Unhealthy", "#ef4444"),
    (300, "Very unhealthy", "#a855f7"),
    (500, "Hazardous", "#7f1d1d"),
)


def pm25_to_aqi(pm25):
    """AQI for a PM2.5 concentration in µg/m³. Works on scalars and arrays."""
    return np.interp(np.clip(pm25, 0, None), _PM25_C, _PM25_I)


def pm10_to_aqi(pm10):
    """AQI for a PM10 concentration in µg/m³. Works on scalars and arrays."""
    return np.interp(np.clip(pm10, 0, None), _PM10_C, _PM10_I)


def category(aqi: float) -> tuple[str, str]:
    """(name, hex color) of the AQI category."""
    for upper, name, color in CATEGORIES:
        if aqi <= upper:
            return name, color
    return CATEGORIES[-1][1], CATEGORIES[-1][2]
