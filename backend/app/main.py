"""FastAPI application entry point."""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import chat, health, sandbox
from backend.app.config import get_settings


def _configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    # Keep uvicorn noise down unless debugging.
    if level != "DEBUG":
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    _configure_logging()
    settings = get_settings()

    app = FastAPI(title="Revenue Leakage Agent", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    # Chat mounts at the root: the frozen frontend contract is POST {API_URL}/chat.
    app.include_router(chat.router)
    app.include_router(sandbox.router, prefix="/api")
    return app


app = create_app()
