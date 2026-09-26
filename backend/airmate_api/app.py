"""Application factory. ``main.py`` builds the app from the environment; tests pass their own Settings."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from airmate_ml.engine import RiskEngine
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import routers
from .bus import Bus
from .config import Settings, get_settings
from .db import Database
from .deps import AppState
from .services import checkin, seed
from .services.grok import GrokClient
from .services.risk import RiskService

log = logging.getLogger("airmate")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings.database_url)
    bus = Bus()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bus.bind(asyncio.get_running_loop())
        db.create_all()
        if settings.airmate_seed and seed.seed_if_empty(db):
            log.info("Seeded demo data")
        engine = await asyncio.to_thread(RiskEngine, settings.airmate_model_path)
        state = AppState(settings=settings, db=db, bus=bus, engine=engine,
                         risk=RiskService(engine, db, bus, settings), grok=GrokClient(settings))
        app.state.airmate = state
        checkin.register(state)
        log.info("Airmate API ready (risk model: %s, Grok: %s)", engine.meta["name"],
                 "on" if settings.grok_enabled else "off, using templates")
        yield
        await state.grok.close()

    app = FastAPI(title="Airmate API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in routers.ALL:
        app.include_router(router, prefix="/api")

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        state: AppState = app.state.airmate
        return {"ok": True, "ts": time.time(), "model": state.engine.meta, "grok": settings.grok_enabled,
                "database": settings.database_url.split(":", 1)[0]}

    # The exported Next.js site (web/out), so one process serves the whole demo.
    if settings.web_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.web_dist, html=True), name="web")
    return app
