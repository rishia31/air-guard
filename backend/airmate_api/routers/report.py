"""Doctor report: a shareable summary of the last N days for the person's clinician.

OWNER: A4 (community-care). Endpoints and shapes are the contract in docs/API.md; bodies are stubs.
Store the payload in the ``reports`` table under an unguessable token (secrets.token_urlsafe).
The written summary comes from Grok (settings.grok_report_model) with an offline template fallback,
and must pass services/safety.invented_doses() against the action plan.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["report"])
NOT_YET = "Not implemented yet (owner: A4 community-care)"


class ReportIn(BaseModel):
    days: int = Field(default=30, ge=1, le=90)
    send_to: str | None = None  # doctor's email, recorded in reports.sent_to (no mail is sent)


class ReportLinkOut(BaseModel):
    token: str
    url: str  # {public_web_url}/report/?token=...


class DailyRow(BaseModel):
    date: str  # YYYY-MM-DD, person's local time
    puffs: int
    symptoms: int
    max_score: int
    mean_score: float
    night_symptoms: int


class ReportOut(BaseModel):
    token: str
    created_at: float
    user: dict  # name, age, triggers, doctor_name, action_plan
    period_days: int
    summary: str  # plain-language paragraph for the doctor
    totals: dict  # puffs, symptoms, high_risk_hours, checkins, emergencies, rescue_days
    daily: list[DailyRow]
    top_factors: list[dict]  # [{"key", "label", "share"}] which exposures drove risk
    exposure_notes: list[str]  # e.g. "PM10 spikes most evenings 6-8 pm (cooking)"
    disclaimer: str


@router.post("/users/{user_id}/reports", response_model=ReportLinkOut)
async def create_report(user_id: str, body: ReportIn) -> ReportLinkOut:
    raise HTTPException(501, NOT_YET)


@router.get("/reports/{token}", response_model=ReportOut)
def read_report(token: str) -> ReportOut:
    raise HTTPException(501, NOT_YET)
