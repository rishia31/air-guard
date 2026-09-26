"""Grok agent: chat with tools, text to speech, realtime voice, check-in answers, emergencies.

OWNER: A1 (agent-voice). Endpoints and shapes are the contract in docs/API.md; the bodies are stubs.
Every user-facing text passes through services/safety.py: red flags -> emergency_script (verbatim),
and invented_doses() must be empty against the person's action plan or the reply is replaced.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, WebSocket
from pydantic import BaseModel, Field

router = APIRouter(tags=["agent"])
NOT_YET = "Not implemented yet (owner: A1 agent-voice)"


class ChatIn(BaseModel):
    user_id: str
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None  # the previous reply's conversation_id, to continue
    speak: bool = False  # also synthesize the reply; audio_url is then set


class ChatOut(BaseModel):
    reply: str
    conversation_id: str | None = None
    emergency: bool = False  # a red flag fired; ``reply`` is the fixed emergency script
    red_flags: list[str] = []
    tool_calls: list[dict] = []  # [{"name", "arguments", "result"}] for the UI to show what Airmate did
    audio_url: str | None = None


class TtsIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: str | None = None


class CheckinAnswerIn(BaseModel):
    answer: str  # "ok" | "not_ok" | "used_inhaler" | free text (safety-checked)
    user_id: str


class EmergencyIn(BaseModel):
    text: str | None = None
    lat: float | None = None
    lon: float | None = None


@router.post("/agent/chat", response_model=ChatOut)
async def chat(body: ChatIn) -> ChatOut:
    raise HTTPException(501, NOT_YET)


@router.post("/agent/tts")
async def tts(body: TtsIn):
    """Returns audio/mpeg bytes."""
    raise HTTPException(501, NOT_YET)


@router.websocket("/agent/voice")
async def voice(ws: WebSocket, user_id: str):
    """Relay between the browser microphone and Grok's realtime voice API (protocol in docs/API.md)."""
    await ws.close(code=1011, reason=NOT_YET)


@router.post("/checkins/{checkin_id}/answer")
async def answer_checkin(checkin_id: int, body: CheckinAnswerIn) -> dict:
    raise HTTPException(501, NOT_YET)


@router.post("/users/{user_id}/emergency")
async def emergency(user_id: str, body: EmergencyIn) -> dict:
    raise HTTPException(501, NOT_YET)
