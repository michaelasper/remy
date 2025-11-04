"""Application configuration helpers."""

from __future__ import annotations

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


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
