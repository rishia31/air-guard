"""Shared application state and FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .bus import Bus
from .config import Settings
from .db import Database
from .models import User
from .services.grok import GrokClient

if TYPE_CHECKING:
    from airmate_ml.engine import RiskEngine

    from .services.risk import RiskService


@dataclass
class AppState:
    settings: Settings
    db: Database
    bus: Bus
    engine: RiskEngine
    risk: RiskService
    grok: GrokClient


def get_state(request: Request) -> AppState:
    return request.app.state.airmate


def get_session(state: AppState = Depends(get_state)) -> Iterator[Session]:
    with state.db.session() as session:
        yield session


def get_user(user_id: str, session: Session = Depends(get_session)) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404, f"No user {user_id!r}")
    return user
