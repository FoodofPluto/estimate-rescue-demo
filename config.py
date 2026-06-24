"""Configuration helpers for Estimate Rescue."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """Load simple KEY=VALUE pairs from .env without requiring python-dotenv."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    admin_password: str | None
    resend_api_key: str | None
    resend_from_email: str | None
    owner_email: str | None
    openai_api_key: str | None
    app_base_url: str | None
    database_path: str


def get_settings() -> Settings:
    """Return current environment-backed settings."""
    return Settings(
        admin_password=os.getenv("ADMIN_PASSWORD"),
        resend_api_key=os.getenv("RESEND_API_KEY"),
        resend_from_email=os.getenv("RESEND_FROM_EMAIL"),
        owner_email=os.getenv("OWNER_EMAIL"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        app_base_url=os.getenv("APP_BASE_URL"),
        database_path=os.getenv("DATABASE_PATH", "estimate_rescue.db"),
    )


settings = get_settings()
