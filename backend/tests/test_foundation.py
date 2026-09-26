"""The core loop every workstream builds on: device -> readings -> risk -> API."""

import time

from airmate_api.app import create_app
from airmate_api.services.seed import DEMO_DEVICE_ID, DEMO_USER_ID
from fastapi.testclient import TestClient

CALM = {"pm25": 6, "pm10": 14, "co2": 650, "tvoc": 120, "temp_c": 22, "humidity": 45}


def _post_minutes(client, reading: dict, minutes: int, device=DEMO_DEVICE_ID):
    batch = [{**reading, "age_s": 60.0 * m} for m in range(minutes, 0, -1)]
    return client.post(f"/api/devices/{device}/readings", json={"readings": batch})


def test_health_and_seed(client):
    health = client.get("/api/health").json()
    assert health["ok"] and health["model"]["name"] == "rules" and health["grok"] is False
    ids = {u["id"] for u in client.get("/api/users").json()}
    assert {"maya", "jordan", "priya"} <= ids
    maya = client.get("/api/users/maya").json()
    assert maya["buddy_id"] == "jordan" and "dust" in maya["triggers"]


def test_readings_produce_a_risk_score(client):
    response = _post_minutes(client, CALM, 30)
    assert response.status_code == 200
    assert response.json()["accepted"] == 30 and response.json()["user_id"] == DEMO_USER_ID
    risk = client.get(f"/api/users/{DEMO_USER_ID}/risk").json()
    assert 0 <= risk["score"] <= 100 and risk["band"] == "low" and risk["color"].startswith("#")
    assert risk["latest"]["pm10"] is not None
    readings = client.get(f"/api/users/{DEMO_USER_ID}/readings?hours=1").json()
    assert len(readings) == 30 and readings[0]["ts"] < readings[-1]["ts"] <= time.time()
    # The next ingest returns the latest score for the device's LED.
    assert _post_minutes(client, CALM, 1).json()["risk"]["band"] == "low"


def test_dust_spike_raises_risk_and_names_dust(client):
    _post_minutes(client, CALM, 30)
    calm = client.get(f"/api/users/{DEMO_USER_ID}/risk?fresh=true").json()
    _post_minutes(client, {**CALM, "pm10": 180}, 8)
    dusty = client.get(f"/api/users/{DEMO_USER_ID}/risk").json()
    assert dusty["score"] > calm["score"]
    assert dusty["factors"][0]["key"] == "dust"
    history = client.get(f"/api/users/{DEMO_USER_ID}/risk/history?hours=1").json()
    assert len(history) >= 2


def test_logging_puffs_and_symptoms(client):
    puff = client.post(f"/api/users/{DEMO_USER_ID}/puffs", json={"count": 2})
    assert puff.status_code == 200 and puff.json()["data"]["count"] == 2
    symptom = client.post(f"/api/users/{DEMO_USER_ID}/symptoms", json={"symptom": "wheeze", "severity": 2})
    assert symptom.status_code == 200
    kinds = [e["kind"] for e in client.get(f"/api/users/{DEMO_USER_ID}/events?kinds=puff,symptom").json()]
    assert sorted(kinds) == ["puff", "symptom"]
    assert client.get(f"/api/users/{DEMO_USER_ID}/risk").json()["puffs_24h"] == 2
    assert client.post(f"/api/users/{DEMO_USER_ID}/symptoms", json={"symptom": "sneezing"}).status_code == 422


def test_device_events_and_unknown_devices(client):
    event = client.post(f"/api/devices/{DEMO_DEVICE_ID}/events", json={"kind": "puff", "data": {"count": 1}})
    assert event.status_code == 200 and event.json()["ok"]
    assert client.post("/api/devices/new-board/readings", json={"readings": [CALM]}).json()["user_id"] == DEMO_USER_ID
    community = client.put("/api/devices/park-1", json={"community": True, "lat": 33.78, "lon": -84.40})
    assert community.status_code == 200
    assert client.post("/api/devices/park-1/readings", json={"readings": [CALM]}).json()["user_id"] is None


def test_device_key(settings):
    settings.device_key = "secret"
    with TestClient(create_app(settings)) as c:
        url = f"/api/devices/{DEMO_DEVICE_ID}/readings"
        assert c.post(url, json={"readings": [CALM]}).status_code == 401
        assert c.post(url, json={"readings": [CALM]}, headers={"X-Device-Key": "secret"}).status_code == 200


def test_triggers_are_validated(client):
    assert client.patch("/api/users/maya", json={"triggers": ["dust", "cats"]}).status_code == 422
    assert client.patch("/api/users/maya", json={"triggers": ["smoke"]}).json()["triggers"] == ["smoke"]


def test_feature_stubs_are_mounted(client):
    # Each owner replaces a 501 with the real thing; the paths themselves are the contract.
    assert client.post("/api/agent/chat", json={"user_id": "maya", "message": "hi"}).status_code in (200, 501)
    assert client.get("/api/community/hotspots").status_code in (200, 501)
    assert client.get("/api/users/maya/buddy").status_code in (200, 501)
    assert client.post("/api/users/maya/reports", json={}).status_code in (200, 501)
