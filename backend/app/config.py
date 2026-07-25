"""Application configuration.

Environment variables are injected via python-dotenv from the project-root
`.env` file (see `.env.example`).
"""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    """Runtime settings resolved from environment variables."""

    def __init__(self) -> None:
        self.anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
        self.anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
        self.data_dir: Path = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
        self.sandbox_dir: Path = Path(os.getenv("SANDBOX_DIR", PROJECT_ROOT / "sandbox"))
        self.backend_host: str = os.getenv("BACKEND_HOST", "127.0.0.1")
        self.backend_port: int = int(os.getenv("BACKEND_PORT", "8000"))
        self.cors_origins: list[str] = os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")


@lru_cache
def get_settings() -> Settings:
    """Return the (cached) application settings."""
    return Settings()
