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
        self._windows: dict[str, HistoryWindow] = {}
        self._deferred: set[str] = set()
        self._tasks: set[asyncio.Task] = set()
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

        A throttled call is not lost: one trailing run is scheduled for when the interval ends, so
        a spike that arrives right after a score still shows up within a few seconds.
        Returns the new assessment, or None when throttled/deferred or the user does not exist.
        """
        now = time.time()
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        wait = self.settings.risk_min_interval_s - (now - self._computed_at.get(user_id, 0.0))
        if not force and (wait > 0 or lock.locked()):
            self._defer(user_id, max(wait, 0.5))
            return None
        async with lock:
            now = time.time()
            self._computed_at[user_id] = now
            loaded = await asyncio.to_thread(self._load, user_id, now)
            if loaded is None:
                return None
            history, (lat, lon) = loaded
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

    def _defer(self, user_id: str, delay: float) -> None:
        if user_id in self._deferred:
            return

        async def run() -> None:
            await asyncio.sleep(delay)
            self._deferred.discard(user_id)
            await self.update(user_id)

        self._deferred.add(user_id)
        task = asyncio.get_running_loop().create_task(run())
        self._tasks.add(task)  # keep a reference so the task isn't garbage-collected
        task.add_done_callback(self._tasks.discard)

    def _load(self, user_id: str, now: float) -> tuple[History, tuple[float | None, float | None]] | None:
        """Runs in a worker thread, under the person's lock."""
        with self.db.session() as session:
            user = session.get(User, user_id)
            if user is None:
                return None
            window = self._windows.setdefault(user_id, HistoryWindow())
            return build_history(session, user, now, window), (user.lat, user.lon)

    def invalidate(self, user_id: str | None = None) -> None:
        """Forget cached history and scores (after deleting or rewriting events, e.g. a reseed)."""
        for cache in (self._windows, self._latest):
            if user_id is None:
                cache.clear()
            else:
                cache.pop(user_id, None)

    def history_points(self, user_id: str, since: float) -> list[dict]:
        with self.db.session() as session:
            rows = session.execute(
                select(Event.ts, Event.data)
                .where(Event.user_id == user_id, Event.kind == "risk", Event.ts >= since)
                .order_by(Event.ts)
            ).all()
        return [{"ts": ts, "score": data["score"], "band": data["band"]} for ts, data in rows]


class HistoryWindow:
    """One person's last week of readings, puffs and symptoms, kept in memory between assessments.

    Decoding a week of 15-second readings from JSON takes ~0.7 s, so each refresh only fetches events
    with a higher id than the last one seen. A periodic full reload covers anything that slipped past
    (rows committed out of id order on Postgres, deletions).
    """

    FULL_RELOAD_S = 600.0

    def __init__(self) -> None:
        self.last_id = 0
        self.loaded_at = 0.0
        self.reading_ts = np.zeros(0)
        self.readings = np.zeros((0, len(SENSORS)))
        self.puff_ts = np.zeros(0)
        self.puff_counts = np.zeros(0)
        self.symptom_ts = np.zeros(0)

    def refresh(self, session: Session, user_id: str, now: float) -> None:
        since = now - HISTORY_DAYS * 86400
        if now - self.loaded_at > self.FULL_RELOAD_S:
            self.__init__()
            self.loaded_at = now
        rows = session.execute(
            select(Event.id, Event.kind, Event.ts, Event.data).where(
                Event.user_id == user_id,
                Event.kind.in_(("reading", "puff", "symptom")),
                Event.id > self.last_id,
                Event.ts > since,
            )
        ).all()
        reading_ts, readings, puff_ts, puff_counts, symptom_ts = [], [], [], [], []
        for event_id, kind, ts, data in rows:
            self.last_id = max(self.last_id, event_id)
            if kind == "reading":
                reading_ts.append(ts)
                readings.append([_num(data.get(name)) for name in SENSORS])
            elif kind == "puff":
                puff_ts.append(ts)
                puff_counts.append(float(data.get("count", 1)))
            else:
                symptom_ts.append(ts)
        keep = self.reading_ts > since
        self.reading_ts = np.concatenate([self.reading_ts[keep], reading_ts])
        self.readings = np.concatenate([self.readings[keep], np.asarray(readings, dtype=np.float64).reshape(-1, len(SENSORS))])
        keep = self.puff_ts > since
        self.puff_ts = np.concatenate([self.puff_ts[keep], puff_ts])
        self.puff_counts = np.concatenate([self.puff_counts[keep], puff_counts])
        self.symptom_ts = np.concatenate([self.symptom_ts[self.symptom_ts > since], symptom_ts])

    def history(self, user: User, now: float) -> History:
        r, p, s = self.reading_ts <= now, self.puff_ts <= now, self.symptom_ts <= now
        return History(
            now=now,
            reading_ts=self.reading_ts[r],
            readings=self.readings[r],
            puff_ts=self.puff_ts[p],
            puff_counts=self.puff_counts[p],
            symptom_ts=self.symptom_ts[s],
            triggers=list(user.triggers or []),
            utc_offset_seconds=utc_offset(user.tz, now),
        )


def build_history(session: Session, user: User, now: float, window: HistoryWindow | None = None) -> History:
    """Everything the engine needs about one person, from the events table.

    Pass the same ``window`` on every call for incremental loading; without one, the week is read in full.
    """
    window = window or HistoryWindow()
    window.refresh(session, user.id, now)
    return window.history(user, now)


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
