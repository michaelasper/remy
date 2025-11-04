"""Application configuration helpers."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Global application settings loaded from environment variables."""

    database_path: Path = Field(
        default=Path("./data/remy.db"),
        description="SQLite database location.",
    )
    home_assistant_base_url: Optional[str] = Field(
        default=None,
        description="Home Assistant base URL.",
    )
    home_assistant_token: Optional[str] = Field(
        default=None,
        description="Long-lived access token.",
    )

    class Config:
        frozen = True


def _load_from_env() -> dict[str, object]:
    """Load optional overrides from environment variables."""

    payload: dict[str, object] = {}
    if (db_path := os.environ.get("REMY_DATABASE_PATH")):
        payload["database_path"] = Path(db_path)
    if (ha_url := os.environ.get("REMY_HOME_ASSISTANT_BASE_URL")):
        payload["home_assistant_base_url"] = ha_url
    if (ha_token := os.environ.get("REMY_HOME_ASSISTANT_TOKEN")):
        payload["home_assistant_token"] = ha_token
    return payload


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings(**_load_from_env())
