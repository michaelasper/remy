"""Simple web UI for interacting with the Remy planning API."""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from remy.server.templates import load as load_template

SAMPLE_CONTEXT = {
    "date": "2025-01-01",
    "prefs": {"diet": "omnivore", "max_time_min": 30, "allergens": []},
    "recent_meals": [],
    "inventory": [
        {"id": 1, "name": "chicken thigh, boneless", "qty": 600, "unit": "g"},
        {"id": 2, "name": "broccoli", "qty": 400, "unit": "g"},
    ],
    "leftovers": [],
    "constraints": {"attendees": 2, "time_window": "evening", "preferred_cuisines": ["mediterranean"]},
    "planner_options": {"recipe_search_enabled": True, "recipe_search_keywords": ["lemon", "herb chicken"]},
}

WEB_APP_PAGE = load_template("webui.html").replace(
    "__SAMPLE_CONTEXT__", json.dumps(SAMPLE_CONTEXT, indent=2)
)

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def ui_home() -> str:
    """Serve the Remy control center SPA."""

    return WEB_APP_PAGE

# Legacy routes now serve the unified SPA for backwards compatibility.
@router.get("/inventory/view", response_class=HTMLResponse)
@router.get("/preferences/view", response_class=HTMLResponse)
@router.get("/receipts/view", response_class=HTMLResponse)
def legacy_views() -> str:
    """Serve the Remy control center SPA for legacy paths."""

    return WEB_APP_PAGE
