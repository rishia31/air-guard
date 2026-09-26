"""Core request/response models: the contract between the backend, the web app, and the device.

docs/API.md documents every endpoint. Change a model here only together with docs/API.md and
web/src/lib/types.ts, and tell the lead (see AGENTS.md). Feature routers (agent, community, buddy,
report) keep their own request/response models next to their endpoints.
"""

from __future__ import annotations

from typing import Literal

from airmate_ml.schema import TRIGGERS
from pydantic import BaseModel, ConfigDict, Field, field_validator

Band = Literal["low", "elevated", "high"]
BAND_COLORS: dict[str, str] = {"low": "#10b981", "elevated": "#f59e0b", "high": "#ef4444"}
SYMPTOMS = ("cough", "wheeze", "chest_tight", "short_breath", "night_waking", "other")


# ---- Device -> backend ---------------------------------------------------------------------------


class ReadingIn(BaseModel):
    """One sensor sample. Omit (or send null for) any sensor the device does not have."""

    ts: float | None = None  # unix seconds (UTC) if the device has NTP time
    age_s: float | None = Field(default=None, ge=0)  # otherwise: how many seconds ago it was taken
    pm25: float | None = None  # µg/m³
    pm10: float | None = None  # µg/m³
    co2: float | None = None  # ppm
    tvoc: float | None = None  # ppb
    temp_c: float | None = None  # °C
    humidity: float | None = None  # % relative humidity


class ReadingBatchIn(BaseModel):
    readings: list[ReadingIn] = Field(min_length=1, max_length=500)
    fw: str | None = None  # firmware version
    rssi: int | None = None  # Wi-Fi signal strength, dBm


class RiskBrief(BaseModel):
    """What the device needs to light its LED ring."""

    score: int
    band: Band
    color: str
    ts: float


class IngestOut(BaseModel):
    user_id: str | None
    accepted: int
    risk: RiskBrief | None = None  # the latest known score; may be a few seconds old


class DeviceEventIn(BaseModel):
    """button: the device button was pressed (data.press = "short" | "long").
    puff: a rescue-inhaler puff was detected (data.count, default 1).
    cough: the night-time cough detector heard coughing (data.count, data.confidence)."""

    kind: Literal["button", "puff", "cough"]
    ts: float | None = None
    data: dict = Field(default_factory=dict)


class DeviceIn(BaseModel):
    user_id: str | None = None
    label: str | None = None
    lat: float | None = None
    lon: float | None = None
    community: bool = False  # anonymous map-only sensor, not attached to a person


class DeviceOut(DeviceIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    last_seen: float | None = None


# ---- People and their logs -----------------------------------------------------------------------


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    role: str
    age: int | None = None
    lat: float | None = None
    lon: float | None = None
    neighborhood: str | None = None
    tz: str
    triggers: list[str]
    action_plan: dict
    buddy_id: str | None = None
    caregiver_ids: list[str]
    cares_for_id: str | None = None
    circle_id: str | None = None
    doctor_name: str | None = None
    doctor_email: str | None = None
    phone: str | None = None
    emergency_contact: dict
    bio: str | None = None


class UserPatch(BaseModel):
    name: str | None = None
    age: int | None = None
    lat: float | None = None
    lon: float | None = None
    neighborhood: str | None = None
    tz: str | None = None
    triggers: list[str] | None = None
    action_plan: dict | None = None
    buddy_id: str | None = None
    doctor_name: str | None = None
    doctor_email: str | None = None
    phone: str | None = None
    emergency_contact: dict | None = None
    bio: str | None = None

    @field_validator("triggers")
    @classmethod
    def _known_triggers(cls, value: list[str] | None) -> list[str] | None:
        unknown = set(value or ()) - set(TRIGGERS)
        if unknown:
            raise ValueError(f"unknown triggers {sorted(unknown)}; use {list(TRIGGERS)}")
        return value


class PuffIn(BaseModel):
    count: int = Field(default=1, ge=1, le=20)
    ts: float | None = None
    source: str = "app"  # app | device | voice | chat


class SymptomIn(BaseModel):
    symptom: Literal["cough", "wheeze", "chest_tight", "short_breath", "night_waking", "other"]
    severity: int = Field(default=1, ge=1, le=3)  # 1 mild, 2 moderate, 3 severe
    note: str | None = None
    ts: float | None = None
    source: str = "app"


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str | None
    device_id: str | None
    kind: str
    ts: float
    data: dict
    lat: float | None = None
    lon: float | None = None


# ---- Risk ----------------------------------------------------------------------------------------


class Factor(BaseModel):
    key: str  # explanation group, see airmate_ml.schema.EXPLAIN_GROUPS
    label: str
    points: float  # risk points this factor adds over a normal day
    detail: str | None = None  # e.g. "Dust (PM10) is 7.1× your normal (180 vs 25 µg/m³)"


class RiskOut(BaseModel):
    user_id: str
    ts: float
    score: int  # 0-100 = P(rescue inhaler needed within 4 h) × 100
    band: Band
    color: str
    probabilities: dict[str, float] | None = None  # {"1h", "4h", "12h"}; None on the rule-based fallback
    factors: list[Factor] = []
    latest: dict[str, float | None] = {}  # latest reading per sensor
    normal: dict[str, float] = {}  # the person's own baseline for pm25, pm10, tvoc
    ratios: dict[str, float] = {}  # latest / normal
    sensors_available: list[str] = []
    outdoor: dict[str, float | None] = {}
    puffs_24h: int = 0
    symptoms_24h: int = 0
    normal_day_score: float | None = None
    rule_score: int
    model: dict = {}


class RiskPoint(BaseModel):
    ts: float
    score: int
    band: Band


class ReadingPoint(BaseModel):
    ts: float
    pm25: float | None = None
    pm10: float | None = None
    co2: float | None = None
    tvoc: float | None = None
    temp_c: float | None = None
    humidity: float | None = None
