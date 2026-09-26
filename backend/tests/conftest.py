import pytest
from airmate_api.app import create_app
from airmate_api.config import Settings
from fastapi.testclient import TestClient


@pytest.fixture
def settings(tmp_path) -> Settings:
    # _env_file=None: tests never read the developer's .env (no Grok calls, no real database).
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        airmate_offline=True,
        airmate_seed=True,
        airmate_model_path=tmp_path / "no-model.pt",  # rule-based fallback: fast and deterministic
        risk_min_interval_s=0,
        xai_api_key=None,
        web_dist=tmp_path / "no-web",
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c
