"""Asthma buddies: matching, the buddy's phone view, and answering a nudge.

OWNER: A4 (community-care). Endpoints and shapes are the contract in docs/API.md; bodies are stubs.
A1 creates nudges (``buddy_nudge`` alerts) when a check-in goes unanswered; this router shows and
acknowledges them.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..schemas import RiskBrief

router = APIRouter(tags=["buddy"])
NOT_YET = "Not implemented yet (owner: A4 community-care)"


class BuddyPerson(BaseModel):
    id: str
    name: str
    neighborhood: str | None = None
    triggers: list[str] = []
    risk: RiskBrief | None = None
    last_seen: float | None = None


class BuddyStatusOut(BaseModel):
    me: BuddyPerson
    buddy: BuddyPerson | None = None
    open_nudges: list[dict] = []  # alert events addressed to me that I have not acknowledged


class MatchOut(BaseModel):
    user_id: str
    name: str
    score: float  # 0-1
    reasons: list[str]  # e.g. ["Both sensitive to dust", "10 minutes apart"]


class PairIn(BaseModel):
    user_id: str
    buddy_id: str


class NudgeAckIn(BaseModel):
    user_id: str  # the buddy acknowledging
    action: Literal["on_my_way", "calling", "checked_ok"]


@router.get("/users/{user_id}/buddy", response_model=BuddyStatusOut)
def buddy_status(user_id: str) -> BuddyStatusOut:
    raise HTTPException(501, NOT_YET)


@router.get("/buddy/matches", response_model=list[MatchOut])
def matches(user_id: str) -> list[MatchOut]:
    raise HTTPException(501, NOT_YET)


@router.post("/buddy/pair")
def pair(body: PairIn) -> dict:
    raise HTTPException(501, NOT_YET)


@router.post("/buddy/nudges/{alert_id}/ack")
def ack_nudge(alert_id: int, body: NudgeAckIn) -> dict:
    raise HTTPException(501, NOT_YET)
