"""Application configuration helpers."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
    api_token: Optional[str] = Field(
        default=None,
        description="Bearer token required for authenticated endpoints.",
    )
    log_level: str = Field(default="INFO", description="Logging level (DEBUG/INFO/WARNING/ERROR)")

    model_config = ConfigDict(frozen=True)


def _load_from_env() -> dict[str, object]:
    """Load optional overrides from environment variables."""

    payload: dict[str, object] = {}
    if (db_path := os.environ.get("REMY_DATABASE_PATH")):
        payload["database_path"] = Path(db_path)
    if (ha_url := os.environ.get("REMY_HOME_ASSISTANT_BASE_URL")):
        payload["home_assistant_base_url"] = ha_url
    if (ha_token := os.environ.get("REMY_HOME_ASSISTANT_TOKEN")):
        payload["home_assistant_token"] = ha_token
    if (api_token := os.environ.get("REMY_API_TOKEN")):
        payload["api_token"] = api_token
    if (log_level := os.environ.get("REMY_LOG_LEVEL")):
        payload["log_level"] = log_level
    return payload


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings(**_load_from_env())
