"""Outdoor air quality, pollen and weather for a location.

OWNER: A2 (ml-demo). Stub: returns "unknown" for everything, which the model handles by using its
defaults. Replace with Open-Meteo (no key; air-quality + pollen + weather APIs), with AirNow /
Google Pollen when their keys are set, cached per ~1 km cell for ~15 minutes. Must return quickly
and never raise: on any error or when ``settings.airmate_offline`` is set, return the unknown dict.
"""

from __future__ import annotations

from airmate_ml.schema import OUTDOOR

from ..config import Settings


async def get_outdoor(lat: float | None, lon: float | None, settings: Settings) -> dict[str, float | None]:
    """{"aqi", "pollen" (0-5), "temp_c", "humidity"}; None means unknown."""
    return {key: None for key in OUTDOOR}
