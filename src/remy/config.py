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
    log_format: str = Field(
        default="plain",
        description="Logging format (plain/json).",
    )
    log_requests: bool = Field(
        default=True,
        description="Emit request access logs when true.",
    )
    ocr_worker_enabled: bool = Field(
        default=False,
        description="Run the background OCR worker when true.",
    )
    ocr_worker_poll_interval: float = Field(
        default=5.0,
        description="Seconds between OCR worker polling iterations.",
    )
    ocr_worker_batch_size: int = Field(
        default=5,
        description="Maximum number of receipts to claim per OCR worker iteration.",
    )
    ocr_default_lang: str = Field(
        default="eng",
        description="Default Tesseract language code for OCR processing.",
    )
    ocr_archive_path: Path = Field(
        default=Path("./data/receipts_archive"),
        description="Directory used to store archived receipt blobs after OCR.",
    )

    model_config = ConfigDict(frozen=True)


def _coerce_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
    if (log_format := os.environ.get("REMY_LOG_FORMAT")):
        payload["log_format"] = log_format
    if (log_requests := os.environ.get("REMY_LOG_REQUESTS")):
        payload["log_requests"] = _coerce_bool(log_requests)
    if (ocr_worker_enabled := os.environ.get("REMY_OCR_WORKER_ENABLED")):
        payload["ocr_worker_enabled"] = _coerce_bool(ocr_worker_enabled)
    if (ocr_worker_poll_interval := os.environ.get("REMY_OCR_WORKER_POLL_INTERVAL")):
        try:
            payload["ocr_worker_poll_interval"] = float(ocr_worker_poll_interval)
        except ValueError:
            pass
    if (ocr_worker_batch_size := os.environ.get("REMY_OCR_WORKER_BATCH_SIZE")):
        try:
            payload["ocr_worker_batch_size"] = int(ocr_worker_batch_size)
        except ValueError:
            pass
    if (ocr_lang := os.environ.get("REMY_OCR_LANG")):
        payload["ocr_default_lang"] = ocr_lang
    if (archive_path := os.environ.get("REMY_OCR_ARCHIVE_PATH")):
        payload["ocr_archive_path"] = Path(archive_path)
    return payload


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings(**_load_from_env())
