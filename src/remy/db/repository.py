"""Database repositories and helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from remy.config import get_settings

_engine: Engine | None = None


def get_engine(database_path: Path | None = None) -> Engine:
    """Return a shared SQLAlchemy engine."""
    global _engine

    if _engine is not None:
        return _engine

    settings = get_settings()
    db_path = database_path or settings.database_path
    _engine = create_engine(f"sqlite:///{db_path}", future=True)
    return _engine


def init_schema(engine: Engine | None = None) -> None:
    """
    Initialize database schema placeholders.

    Actual ORM models should create metadata and call metadata.create_all(engine).
    """
    # TODO: define SQLAlchemy models and create tables.
    _ = engine or get_engine()
