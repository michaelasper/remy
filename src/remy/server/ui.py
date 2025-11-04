"""Simple web UI for interacting with the Remy planning API."""

from __future__ import annotations

import html
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
    "constraints": {"attendees": 2, "time_window": "evening"},
}

ESCAPED_SAMPLE_CONTEXT = html.escape(json.dumps(SAMPLE_CONTEXT, indent=2))

NAVIGATION = """
      <nav>
        <a href="/">Planner</a>
        <a href="/inventory/view">Inventory</a>
        <a href="/preferences/view">Preferences</a>
      </nav>
"""

HTML_PAGE = (
    load_template("planner.html")
    .replace("__NAVIGATION__", NAVIGATION)
    .replace("__SAMPLE_CONTEXT__", ESCAPED_SAMPLE_CONTEXT)
)

INVENTORY_PAGE = load_template("inventory.html").replace("__NAVIGATION__", NAVIGATION)

PREFERENCES_PAGE = load_template("preferences.html").replace("__NAVIGATION__", NAVIGATION)

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def ui_home() -> str:
    """Serve the Remy planner workspace."""

    return HTML_PAGE


@router.get("/inventory/view", response_class=HTMLResponse)
def inventory_view() -> str:
    """Serve an HTML view of the current inventory."""

    return INVENTORY_PAGE


@router.get("/preferences/view", response_class=HTMLResponse)
def preferences_view() -> str:
    """Serve the preferences management page."""

    return PREFERENCES_PAGE
