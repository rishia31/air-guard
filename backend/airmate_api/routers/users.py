"""People, their logs (puffs, symptoms), readings, and risk."""

from __future__ import annotations

import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import AppState, get_session, get_state, get_user
from ..models import Event, User
from ..schemas import EventOut, PuffIn, ReadingPoint, RiskOut, RiskPoint, SymptomIn, UserOut, UserPatch

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(session: Session = Depends(get_session)) -> list[User]:
    return list(session.scalars(select(User).order_by(User.created_at)))


@router.get("/{user_id}", response_model=UserOut)
def read_user(user: User = Depends(get_user)) -> User:
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    body: UserPatch,
    background: BackgroundTasks,
    user: User = Depends(get_user),
    session: Session = Depends(get_session),
    state: AppState = Depends(get_state),
) -> User:
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    session.commit()
    if body.triggers is not None:
        background.add_task(state.risk.update, user.id, force=True)
    return user


def _log(session: Session, state: AppState, user: User, kind: str, ts: float | None, data: dict) -> Event:
    now = time.time()
    event = Event(user_id=user.id, kind=kind, ts=min(ts or now, now), data=data, lat=user.lat, lon=user.lon)
    session.add(event)
    session.commit()
    state.bus.user(user.id, "event", {"id": event.id, "kind": kind, "ts": event.ts, "data": data})
    return event


@router.post("/{user_id}/puffs", response_model=EventOut)
def log_puff(
    body: PuffIn,
    background: BackgroundTasks,
    user: User = Depends(get_user),
    session: Session = Depends(get_session),
    state: AppState = Depends(get_state),
) -> Event:
    event = _log(session, state, user, "puff", body.ts, {"count": body.count, "source": body.source})
    background.add_task(state.risk.update, user.id, force=True)
    return event


@router.post("/{user_id}/symptoms", response_model=EventOut)
def log_symptom(
    body: SymptomIn,
    background: BackgroundTasks,
    user: User = Depends(get_user),
    session: Session = Depends(get_session),
    state: AppState = Depends(get_state),
) -> Event:
    data = body.model_dump(exclude={"ts"})
    event = _log(session, state, user, "symptom", body.ts, data)
    background.add_task(state.risk.update, user.id, force=True)
    return event


@router.get("/{user_id}/events", response_model=list[EventOut])
def list_events(
    user: User = Depends(get_user),
    session: Session = Depends(get_session),
    kinds: str | None = Query(default=None, description="Comma-separated, e.g. puff,symptom,checkin"),
    since: float | None = None,
    limit: int = Query(default=200, le=5000),
) -> list[Event]:
    query = select(Event).where(Event.user_id == user.id)
    if kinds:
        query = query.where(Event.kind.in_([k.strip() for k in kinds.split(",") if k.strip()]))
    if since is not None:
        query = query.where(Event.ts >= since)
    return list(session.scalars(query.order_by(Event.ts.desc()).limit(limit)))


@router.get("/{user_id}/readings", response_model=list[ReadingPoint])
def list_readings(
    user: User = Depends(get_user),
    session: Session = Depends(get_session),
    hours: float = Query(default=6, gt=0, le=24 * 7),
) -> list[ReadingPoint]:
    rows = session.execute(
        select(Event.ts, Event.data)
        .where(Event.user_id == user.id, Event.kind == "reading", Event.ts >= time.time() - hours * 3600)
        .order_by(Event.ts)
    ).all()
    return [ReadingPoint(ts=ts, **data) for ts, data in rows]


@router.get("/{user_id}/risk", response_model=RiskOut)
async def current_risk(user_id: str, state: AppState = Depends(get_state), fresh: bool = False) -> dict:
    """The latest assessment; computed on the spot if there is none yet (or ``fresh=true``)."""
    assessment = None if fresh else state.risk.latest(user_id)
    if assessment is None:
        assessment = await state.risk.update(user_id, force=True)
    if assessment is None:
        raise HTTPException(404, f"No user {user_id!r}")
    return assessment


@router.get("/{user_id}/risk/history", response_model=list[RiskPoint])
def risk_history(
    user: User = Depends(get_user),
    state: AppState = Depends(get_state),
    hours: float = Query(default=24, gt=0, le=24 * 30),
) -> list[dict]:
    return state.risk.history_points(user.id, time.time() - hours * 3600)
