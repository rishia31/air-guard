"""The core loop every workstream builds on: device -> readings -> risk -> API."""

import time

import numpy as np
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


def test_incremental_history_matches_a_full_reload(client):
    from airmate_api.models import User
    from airmate_api.services.risk import HistoryWindow, build_history

    state = client.app.state.airmate
    window = HistoryWindow()
    _post_minutes(client, CALM, 20)
    client.post(f"/api/users/{DEMO_USER_ID}/puffs", json={"count": 2})
    with state.db.session() as session:
        maya = session.get(User, DEMO_USER_ID)
        build_history(session, maya, time.time(), window)
    # New readings, including a late backfill with an old timestamp, and a symptom.
    _post_minutes(client, {**CALM, "pm10": 180}, 5)
    client.post(f"/api/devices/{DEMO_DEVICE_ID}/readings", json={"readings": [{**CALM, "age_s": 3 * 3600}]})
    client.post(f"/api/users/{DEMO_USER_ID}/symptoms", json={"symptom": "cough"})
    now = time.time()
    with state.db.session() as session:
        maya = session.get(User, DEMO_USER_ID)
        incremental = build_history(session, maya, now, window)
        full = build_history(session, maya, now)
    order_i, order_f = np.argsort(incremental.reading_ts), np.argsort(full.reading_ts)
    assert len(incremental.reading_ts) == len(full.reading_ts) == 26
    assert np.array_equal(incremental.reading_ts[order_i], full.reading_ts[order_f])
    assert np.array_equal(incremental.readings[order_i], full.readings[order_f], equal_nan=True)
    assert incremental.puff_counts.sum() == full.puff_counts.sum() == 2
    assert len(incremental.symptom_ts) == len(full.symptom_ts) == 1


def test_personal_devices_never_publish_location_to_the_community(client, monkeypatch):
    state = client.app.state.airmate
    published = []
    monkeypatch.setattr(state.bus, "publish", lambda topic, kind, data: published.append((topic, data)))
    _post_minutes(client, CALM, 1)  # Maya's bedroom device has lat/lon (her home)
    assert {topic for topic, _ in published} == {"user:maya"}  # the reading and the new risk score
    client.put("/api/devices/park-1", json={"community": True, "lat": 33.78, "lon": -84.40})
    client.post("/api/devices/park-1/readings", json={"readings": [CALM]})
    community = [data for topic, data in published if topic == "community"]
    assert len(community) == 1 and community[0]["device_id"] == "park-1"


def test_throttled_updates_run_later_instead_of_being_dropped(settings):
    import asyncio

    settings.risk_min_interval_s = 1.0
    with TestClient(create_app(settings)) as c:
        _post_minutes(c, CALM, 10)  # scores now
        _post_minutes(c, {**CALM, "pm10": 180}, 1)  # inside the interval: deferred, not dropped
        assert len(c.get(f"/api/users/{DEMO_USER_ID}/risk/history?hours=1").json()) == 1
        c.portal.call(asyncio.sleep, 1.5)  # let the app's event loop run the trailing update
        history = c.get(f"/api/users/{DEMO_USER_ID}/risk/history?hours=1").json()
        assert len(history) == 2 and history[1]["score"] > history[0]["score"]
