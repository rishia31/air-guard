from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env", ".env"), extra="ignore")

    # Storage: SQLite by default; set a Supabase/Postgres URL to use a hosted database.
    database_url: str = f"sqlite:///{REPO_ROOT / 'backend' / 'data' / 'airmate.db'}"

    # Grok (xAI). Without a key the agent, advice and report summaries fall back to offline templates.
    xai_api_key: str | None = None
    xai_base_url: str = "https://api.x.ai/v1"
    xai_realtime_url: str = "wss://api.x.ai/v1/realtime"
    grok_chat_model: str = "grok-4.3"
    grok_chat_reasoning: str = "none"
    grok_report_model: str = "grok-4.7"
    grok_report_reasoning: str = "low"
    grok_voice_model: str = "grok-voice-latest"
    grok_voice: str = "eve"
    grok_voice_reasoning: str = "none"

    # Outside data. Open-Meteo needs no key and is used whenever these are missing.
    airnow_api_key: str | None = None
    google_pollen_api_key: str | None = None

    # Push notifications to buddies/caregivers through ntfy (install the ntfy app and subscribe
    # to "<prefix>-<user id>"). Leave unset to only use in-app alerts.
    ntfy_server: str = "https://ntfy.sh"
    ntfy_topic_prefix: str | None = None

    device_key: str | None = None  # if set, devices must send it in the X-Device-Key header
    default_user_id: str = "maya"  # unknown devices are attached to this user
    public_web_url: str = "http://localhost:8000"
    cors_origins: str = "*"
    web_dist: Path = REPO_ROOT / "web" / "out"

    airmate_offline: bool = False  # skip outside-data and map lookups (tests, no Wi-Fi)
    airmate_seed: bool = True  # seed demo users and a week of data when the database is empty
    airmate_model_path: Path | None = None  # defaults to the artifact shipped in ml/airmate_ml/artifacts

    risk_min_interval_s: float = 4.0
    high_risk_score: int = 45
    # Check in on a sudden jump too, not only above high_risk_score: scores usually sit in single digits,
    # so a dust spike that moves 5 -> 20 matters even though it never crosses 45.
    checkin_jump_points: int = 12
    checkin_jump_window_s: int = 30 * 60
    checkin_cooldown_s: int = 15 * 60
    buddy_nudge_delay_s: int = 120  # nudge the buddy if the patient ignores Airmate's check-in

    @property
    def grok_enabled(self) -> bool:
        return bool(self.xai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
