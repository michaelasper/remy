"""Shared helpers for integration tests."""

from __future__ import annotations

from remy.config import get_settings


def auth_headers() -> dict[str, str]:
    token = get_settings().api_token
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}
