"""Database tables. Readings, puffs, symptoms, check-ins, risk scores and alerts all live in ``events``."""

from __future__ import annotations

import time

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default="patient")  # patient | caregiver
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tz: Mapped[str] = mapped_column(String(64), default="America/New_York")
    triggers: Mapped[list] = mapped_column(JSON, default=list)  # self-reported, see airmate_ml.schema.TRIGGERS
    action_plan: Mapped[dict] = mapped_column(JSON, default=dict)  # green/yellow/red zones from the doctor
    buddy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    caregiver_ids: Mapped[list] = mapped_column(JSON, default=list)
    cares_for_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    circle_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doctor_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    doctor_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    emergency_contact: Mapped[dict] = mapped_column(JSON, default=dict)  # name, phone, relation
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    community: Mapped[bool] = mapped_column(Boolean, default=False)  # anonymous map-only device
    last_seen: Mapped[float | None] = mapped_column(Float, nullable=True)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_user_kind_ts", "user_id", "kind", "ts"), Index("ix_events_kind_ts", "kind", "ts"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # reading | puff | symptom | checkin | risk | alert | button | cough | emergency
    kind: Mapped[str] = mapped_column(String(20))
    ts: Mapped[float] = mapped_column(Float)  # unix seconds (UTC)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)


class Report(Base):
    __tablename__ = "reports"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    sent_to: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)


class Circle(Base):
    __tablename__ = "circles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class CirclePost(Base):
    __tablename__ = "circle_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    circle_id: Mapped[str] = mapped_column(ForeignKey("circles.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    ts: Mapped[float] = mapped_column(Float, default=time.time)
