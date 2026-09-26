"""Entry point: ``uv run airmate-api`` or ``uv run uvicorn airmate_api.main:app --reload``."""

from __future__ import annotations

import logging
import os

from .app import create_app

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("airmate_api.main:app", host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8000")))
