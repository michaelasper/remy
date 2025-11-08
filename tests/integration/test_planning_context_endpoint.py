"""Integration tests for assembling planning context from persisted data."""

from __future__ import annotations

from datetime import date

from fastapi import status

from remy.config import get_settings
from remy.db.meals import record_meal
from remy.db.preferences import save_preferences
from remy.models.context import Preferences, RecentMeal


def _auth_headers():
    token = get_settings().api_token
    return {"Authorization": f"Bearer {token}"} if token else {}


def _iso_today() -> str:
    return date.today().isoformat()


def test_planning_context_endpoint_uses_db_data(client):
    save_preferences(Preferences(diet="vegan", max_time_min=20, allergens=["peanut"]))
    record_meal(RecentMeal(date=date.today(), title="Test Chili", rating=4))

    response = client.get(
        "/planning-context",
        params={
            "date": "2025-11-07",
            "attendees": 3,
            "time_window": "evening",
            "recent_meals": 1,
        },
        headers=_auth_headers(),
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["date"] == "2025-11-07"
    assert payload["prefs"]["diet"] == "vegan"
    assert payload["prefs"]["max_time_min"] == 20
    assert payload["prefs"]["allergens"] == ["peanut"]
    assert payload["constraints"]["attendees"] == 3
    assert payload["constraints"]["time_window"] == "evening"
    assert len(payload["recent_meals"]) == 1
    assert isinstance(payload["inventory"], list) and payload["inventory"]


def test_planning_context_defaults_when_params_missing(client):
    response = client.get("/planning-context", headers=_auth_headers())

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["date"] == _iso_today()
    assert payload["constraints"]["attendees"] is None
    assert payload["constraints"]["time_window"] is None
