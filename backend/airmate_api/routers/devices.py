"""Device ingest: the ESP32 and scripts/device_sim.py both talk to these endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..deps import AppState, get_session, get_state
from ..models import Device, Event, User
from ..schemas import DeviceEventIn, DeviceIn, DeviceOut, IngestOut, ReadingBatchIn, RiskBrief
from ..services import checkin

router = APIRouter(prefix="/devices", tags=["devices"])
MAX_AGE_S = 7 * 86400


def _check_key(state: AppState, key: str | None) -> None:
    if state.settings.device_key and key != state.settings.device_key:
        raise HTTPException(401, "Missing or wrong X-Device-Key")


def _device(session: Session, state: AppState, device_id: str) -> Device:
    """Look up a device; unknown devices are attached to the default (demo) user."""
    device = session.get(Device, device_id)
    if device is None:
        owner = state.settings.default_user_id
        device = Device(id=device_id, user_id=owner if session.get(User, owner) else None)
        session.add(device)
    return device


def _event_ts(ts: float | None, age_s: float | None, now: float) -> float:
    if ts is not None and 0 <= now - ts < MAX_AGE_S:
        return ts
    if age_s is not None:
        return now - min(age_s, MAX_AGE_S)
    return now  # no clock on the device (or a clearly wrong one): use arrival time


def risk_brief(assessment: dict | None) -> RiskBrief | None:
    if not assessment:
        return None
    return RiskBrief(score=assessment["score"], band=assessment["band"], color=assessment["color"],
                     ts=assessment["ts"])


@router.post("/{device_id}/readings", response_model=IngestOut)
def ingest_readings(
    device_id: str,
    body: ReadingBatchIn,
    background: BackgroundTasks,
    state: AppState = Depends(get_state),
    session: Session = Depends(get_session),
    x_device_key: str | None = Header(default=None),
) -> IngestOut:
    _check_key(state, x_device_key)
    device = _device(session, state, device_id)
    now = time.time()
    newest: tuple[float, dict] | None = None
    for reading in body.readings:
        ts = _event_ts(reading.ts, reading.age_s, now)
        data = reading.model_dump(exclude={"ts", "age_s"})
        session.add(Event(user_id=device.user_id, device_id=device.id, kind="reading", ts=ts, data=data,
                          lat=device.lat, lon=device.lon))
        if newest is None or ts >= newest[0]:
            newest = (ts, data)
    device.last_seen = now
    session.commit()

    if newest is not None:
        payload = {"device_id": device.id, "ts": newest[0], **newest[1]}
        if device.user_id:
            state.bus.user(device.user_id, "reading", payload)
        if device.community or device.lat is not None:
            state.bus.publish("community", "reading", {**payload, "lat": device.lat, "lon": device.lon})
    if device.user_id:
        background.add_task(state.risk.update, device.user_id)
    return IngestOut(user_id=device.user_id, accepted=len(body.readings),
                     risk=risk_brief(state.risk.latest(device.user_id)))


@router.post("/{device_id}/events")
def device_event(
    device_id: str,
    body: DeviceEventIn,
    background: BackgroundTasks,
    state: AppState = Depends(get_state),
    session: Session = Depends(get_session),
    x_device_key: str | None = Header(default=None),
) -> dict:
    _check_key(state, x_device_key)
    device = _device(session, state, device_id)
    now = time.time()
    data = dict(body.data)
    if body.kind == "puff":
        data = {"source": "device", **data, "count": int(data.get("count", 1))}
    event = Event(user_id=device.user_id, device_id=device.id, kind=body.kind, ts=_event_ts(body.ts, None, now),
                  data=data, lat=device.lat, lon=device.lon)
    session.add(event)
    device.last_seen = now
    session.commit()
    if device.user_id:
        state.bus.user(device.user_id, "event", {"id": event.id, "kind": event.kind, "ts": event.ts, "data": data})
        if body.kind == "puff":
            background.add_task(state.risk.update, device.user_id, force=True)
        elif body.kind == "button":
            background.add_task(checkin.on_button, state, device.user_id, str(data.get("press", "short")))
    return {"ok": True, "id": event.id, "risk": risk_brief(state.risk.latest(device.user_id))}


@router.put("/{device_id}", response_model=DeviceOut)
def upsert_device(device_id: str, body: DeviceIn, session: Session = Depends(get_session)) -> Device:
    device = session.get(Device, device_id) or Device(id=device_id)
    for key, value in body.model_dump().items():
        setattr(device, key, value)
    session.add(device)
    session.commit()
    return device


@router.get("", response_model=list[DeviceOut])
def list_devices(session: Session = Depends(get_session)) -> list[Device]:
    return list(session.query(Device).order_by(Device.id))
