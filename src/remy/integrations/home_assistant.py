"""Home Assistant integration scaffolding."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from remy.config import get_settings


class HomeAssistantClient:
    """Minimal client wrapper around the Home Assistant HTTP API."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None) -> None:
        settings = get_settings()
        self._base_url = base_url or settings.home_assistant_base_url
        self._token = token or settings.home_assistant_token

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def notify(self, title: str, message: str) -> None:
        """Send a persistent notification."""
        if not self._base_url:
            raise RuntimeError("Home Assistant base URL is not configured.")

        endpoint = f"{self._base_url}/api/services/persistent_notification/create"
        payload = {"title": title, "message": message}

        with httpx.Client() as client:
            client.post(endpoint, headers=self._headers(), json=payload, timeout=10.0)

    def add_shopping_item(self, name: str) -> None:
        """Add an item to the Home Assistant shopping list."""
        if not self._base_url:
            raise RuntimeError("Home Assistant base URL is not configured.")

        endpoint = f"{self._base_url}/api/shopping_list/item"
        payload: Dict[str, Any] = {"name": name}

        with httpx.Client() as client:
            client.post(endpoint, headers=self._headers(), json=payload, timeout=10.0)
