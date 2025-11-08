"""Integration tests for assembling planning context from persisted data."""

from __future__ import annotations

from datetime import date

from fastapi import status

from remy.config import get_settings
from remy.db.leftovers import create_leftover_item
from remy.db.meals import record_meal
from remy.db.preferences import save_preferences
from remy.models.context import Preferences, RecentMeal

from tests.integration.utils import auth_headers


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
        headers=auth_headers(),
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
    assert payload["planner_options"]["recipe_search_enabled"] in {True, False}


def test_planning_context_defaults_when_params_missing(client):
    response = client.get("/planning-context", headers=auth_headers())

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["date"] == _iso_today()
    assert payload["constraints"]["attendees"] is None
    assert payload["constraints"]["time_window"] is None


def test_planning_context_includes_leftovers(client):
    create_leftover_item(name="garlic mash", quantity=400, unit="g")

    response = client.get("/planning-context", headers=auth_headers())
    assert response.status_code == status.HTTP_200_OK
    leftovers = response.json()["leftovers"]
    assert leftovers
    assert any(item["name"] == "garlic mash" for item in leftovers)


def test_planning_context_supports_preference_overrides(client):
    params = [
        ("diet_override", "keto"),
        ("max_time_min", "20"),
        ("allergens", "peanut"),
        ("allergens", "soy"),
        ("preferred_cuisines", "thai"),
        ("preferred_cuisines", "mexican"),
    ]
    response = client.get("/planning-context", headers=auth_headers(), params=params)
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["prefs"]["diet"] == "keto"
    assert payload["prefs"]["max_time_min"] == 20
    assert payload["prefs"]["allergens"] == ["peanut", "soy"]
    assert payload["constraints"]["preferred_cuisines"] == ["thai", "mexican"]
    assert payload["planner_options"]["recipe_search_enabled"] in {True, False}


def test_planning_context_includes_recipe_search_overrides(client):
    response = client.get(
        "/planning-context",
        headers=auth_headers(),
        params={
            "recipe_search": "true",
            "search_keywords": ["sheet pan", "citrus chicken"],
        },
    )
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["planner_options"]["recipe_search_enabled"] is True
    assert payload["planner_options"]["recipe_search_keywords"] == ["sheet pan", "citrus chicken"]
