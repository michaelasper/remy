"""Database engine and session management."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from remy.config import get_settings
from remy.db.models import Base

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
logger = logging.getLogger(__name__)


def get_engine(database_path: Path | None = None) -> Engine:
    """Return a shared SQLAlchemy engine configured for SQLite."""
    global _engine, _session_factory

    if _engine is not None:
        return _engine

    settings = get_settings()
    db_path = database_path or settings.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        echo=False,
    )
    try:
        Base.metadata.create_all(_engine)
    except OperationalError as exc:
        if "already exists" in str(exc).lower():
            logger.debug("Database schema already initialized: %s", exc)
        else:
            raise
    _session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_session() -> Session:
    """Return a new SQLAlchemy session."""
    global _session_factory

    if _session_factory is None:
        get_engine()
    assert _session_factory is not None  # for mypy
    return _session_factory()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager yielding a session with automatic commit/rollback."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = ["get_engine", "get_session", "session_scope", "reset_repository_state"]


def reset_repository_state() -> None:
    """Reset cached engine/session state (intended for testing)."""

    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
