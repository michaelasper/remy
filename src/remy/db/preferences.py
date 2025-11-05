"""Data access helpers for household preferences."""

from __future__ import annotations

import json
import logging
from typing import Dict

from sqlalchemy import select

from remy.models.context import Preferences

from .models import PreferenceORM
from .repository import session_scope

logger = logging.getLogger(__name__)

PREFERENCE_KEYS = {"diet", "max_time_min", "allergens"}


def _encode_value(value) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return json.dumps(value)


def _decode_value(value: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def load_preferences() -> Preferences:
    """Load stored preferences or return defaults if none set."""

    with session_scope() as session:
        rows = session.execute(select(PreferenceORM)).scalars().all()

        data: Dict[str, object] = {}
        for row in rows:
            decoded = _decode_value(row.value)
            data[row.key] = decoded

    logger.debug("Loaded preferences from DB payload=%s", data)
    return Preferences.model_validate(data)


def save_preferences(prefs: Preferences) -> Preferences:
    """Persist the provided preferences payload."""

    payload = prefs.model_dump()
    logger.debug("Persisting preferences payload=%s", payload)

    with session_scope() as session:
        for key, value in payload.items():
            if key not in PREFERENCE_KEYS:
                continue
            session.merge(PreferenceORM(key=key, value=_encode_value(value)))

    return load_preferences()
