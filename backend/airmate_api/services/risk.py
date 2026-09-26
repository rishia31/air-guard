"""Live risk scoring.

After new readings or logs arrive, ``RiskService.update`` rebuilds the person's last week from the
events table, scores it with the ML engine (off the event loop), stores a ``risk`` event, publishes it
on ``user:<id>``, and then calls every registered listener. The check-in logic (services/checkin.py)
is a listener, so features that react to risk never need to edit this file.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
from airmate_ml.engine import History, RiskEngine
from airmate_ml.schema import HISTORY_DAYS, SENSORS
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..bus import Bus
from ..config import Settings
from ..db import Database
from ..models import Event, User
from ..schemas import BAND_COLORS
from . import outdoor

log = logging.getLogger(__name__)

# listener(user_id, assessment, previous_assessment_or_None)
RiskListener = Callable[[str, dict, dict | None], Awaitable[None]]


class RiskService:
    def __init__(self, engine: RiskEngine, db: Database, bus: Bus, settings: Settings):
        self.engine = engine
        self.db = db
        self.bus = bus
        self.settings = settings
        self.listeners: list[RiskListener] = []
        self._latest: dict[str, dict] = {}
        self._computed_at: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._engine_lock = asyncio.Lock()  # one assessment at a time; Captum explainers are not thread-safe

    def add_listener(self, listener: RiskListener) -> None:
        self.listeners.append(listener)

    def latest(self, user_id: str | None) -> dict | None:
        """The most recent assessment for a person (cached, else the last stored ``risk`` event)."""
        if user_id is None:
            return None
        if user_id not in self._latest:
            with self.db.session() as session:
                data = session.scalars(
                    select(Event.data)
                    .where(Event.user_id == user_id, Event.kind == "risk")
                    .order_by(Event.ts.desc())
                    .limit(1)
                ).first()
            if data is None:
                return None
            self._latest[user_id] = data
        return self._latest[user_id]

    async def update(self, user_id: str, *, force: bool = False) -> dict | None:
        """Re-score a person. Throttled to one run per ``risk_min_interval_s`` unless ``force``.

        Returns the new assessment, or None when throttled or the user does not exist.
        """
        now = time.time()
        if not force and now - self._computed_at.get(user_id, 0.0) < self.settings.risk_min_interval_s:
            return None
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        if lock.locked() and not force:
            return None
        async with lock:
            now = time.time()
            self._computed_at[user_id] = now
            with self.db.session() as session:
                user = session.get(User, user_id)
                if user is None:
                    return None
                history = build_history(session, user, now)
                lat, lon = user.lat, user.lon
            history.outdoor = await outdoor.get_outdoor(lat, lon, self.settings)
            async with self._engine_lock:
                assessment = await asyncio.to_thread(self.engine.assess, history)
            assessment = _jsonable({**assessment, "user_id": user_id, "ts": now,
                                    "color": BAND_COLORS[assessment["band"]]})
            previous = self.latest(user_id)
            with self.db.session() as session:
                session.add(Event(user_id=user_id, kind="risk", ts=now, data=assessment))
                session.commit()
            self._latest[user_id] = assessment

        self.bus.user(user_id, "risk", assessment)
        for listener in list(self.listeners):
            try:
                await listener(user_id, assessment, previous)
            except Exception:
                log.exception("Risk listener %s failed", getattr(listener, "__name__", listener))
        return assessment

    def history_points(self, user_id: str, since: float) -> list[dict]:
        with self.db.session() as session:
            rows = session.execute(
                select(Event.ts, Event.data)
                .where(Event.user_id == user_id, Event.kind == "risk", Event.ts >= since)
                .order_by(Event.ts)
            ).all()
        return [{"ts": ts, "score": data["score"], "band": data["band"]} for ts, data in rows]


def build_history(session: Session, user: User, now: float) -> History:
    """Everything the engine needs about one person, from the events table."""
    rows = session.execute(
        select(Event.kind, Event.ts, Event.data)
        .where(
            Event.user_id == user.id,
            Event.kind.in_(("reading", "puff", "symptom")),
            Event.ts > now - HISTORY_DAYS * 86400,
            Event.ts <= now,
        )
        .order_by(Event.ts)
    ).all()
    reading_ts, readings, puff_ts, puff_counts, symptom_ts = [], [], [], [], []
    for kind, ts, data in rows:
        if kind == "reading":
            reading_ts.append(ts)
            readings.append([_num(data.get(name)) for name in SENSORS])
        elif kind == "puff":
            puff_ts.append(ts)
            puff_counts.append(float(data.get("count", 1)))
        else:
            symptom_ts.append(ts)
    return History(
        now=now,
        reading_ts=np.asarray(reading_ts, dtype=np.float64),
        readings=np.asarray(readings, dtype=np.float64).reshape(-1, len(SENSORS)),
        puff_ts=np.asarray(puff_ts, dtype=np.float64),
        puff_counts=np.asarray(puff_counts, dtype=np.float64),
        symptom_ts=np.asarray(symptom_ts, dtype=np.float64),
        triggers=list(user.triggers or []),
        utc_offset_seconds=utc_offset(user.tz, now),
    )


def utc_offset(tz: str | None, ts: float) -> float:
    try:
        offset = datetime.fromtimestamp(ts, ZoneInfo(tz or "UTC")).utcoffset()
    except Exception:
        return 0.0
    return offset.total_seconds() if offset else 0.0


def _num(value) -> float:
    return float("nan") if value is None else float(value)


def _jsonable(value):
    """Plain JSON types only: numpy scalars become Python numbers, NaN/inf become None."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
