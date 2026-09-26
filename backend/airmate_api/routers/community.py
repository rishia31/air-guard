"""Community: anonymized hotspot map, crowd air reports, and asthma circles.

OWNER: A4 (community-care). Endpoints and shapes are the contract in docs/API.md; bodies are stubs.
Privacy rule: the map never shows a single person's home. Aggregate into ~500 m cells and only show a
cell with at least 2 contributors, or one that holds a community (map-only) device.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["community"])
NOT_YET = "Not implemented yet (owner: A4 community-care)"


class HotspotCell(BaseModel):
    lat: float
    lon: float
    score: int  # 0-100 community air score for the cell
    aqi: int | None = None
    pm25: float | None = None
    pm10: float | None = None
    tvoc: float | None = None
    contributors: int
    puffs: int = 0  # rescue puffs logged in the cell over the window (asthma "heat")
    reports: list[str] = []  # crowd report kinds, e.g. ["smoke"]
    label: str | None = None  # e.g. "Dust is 3× normal around Home Park"


class HotspotsOut(BaseModel):
    generated_at: float
    hours: float
    cells: list[HotspotCell]


class AirReportIn(BaseModel):
    user_id: str | None = None
    lat: float
    lon: float
    kind: Literal["smoke", "dust", "pollen", "odor", "construction", "other"]
    note: str | None = Field(default=None, max_length=280)


class PostIn(BaseModel):
    user_id: str
    text: str = Field(min_length=1, max_length=1000)


class PostOut(BaseModel):
    id: int
    circle_id: str
    user_id: str
    user_name: str
    text: str
    ts: float


@router.get("/community/hotspots", response_model=HotspotsOut)
def hotspots(hours: float = Query(default=6, gt=0, le=72)) -> HotspotsOut:
    raise HTTPException(501, NOT_YET)


@router.post("/community/reports")
def report_air(body: AirReportIn) -> dict:
    raise HTTPException(501, NOT_YET)


@router.get("/circles/{circle_id}/posts", response_model=list[PostOut])
def circle_posts(circle_id: str) -> list[PostOut]:
    raise HTTPException(501, NOT_YET)


@router.post("/circles/{circle_id}/posts", response_model=PostOut)
def add_post(circle_id: str, body: PostIn) -> PostOut:
    raise HTTPException(501, NOT_YET)
