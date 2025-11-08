"""Shared pytest fixtures for the Remy test suite."""

from __future__ import annotations

from datetime import date
from typing import Dict, Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from remy.config import get_settings
from remy.db.repository import reset_repository_state
from remy.models.plan import (
    IngredientRequirement,
    InventoryDelta,
    Plan,
    PlanCandidate,
    ShoppingShortfall,
)
from remy.server.app import create_app


@pytest.fixture()
def app() -> Generator[FastAPI, None, None]:
    """Create a new FastAPI app instance for each test and reset overrides."""

    application = create_app()
    yield application
    application.dependency_overrides.clear()


@pytest.fixture()
def client(app) -> TestClient:
    """Return a test client bound to the FastAPI app."""

    return TestClient(app)


@pytest.fixture()
def sample_context_payload() -> Dict[str, object]:
    """Provide a sample planning context payload for API tests."""

    return {
        "date": date.today().isoformat(),
        "prefs": {"diet": "vegan", "max_time_min": 30, "allergens": []},
        "recent_meals": [],
        "inventory": [
            {
                "id": 101,
                "name": "tofu",
                "qty": 500,
                "unit": "g",
                "best_before": date.today().isoformat(),
            }
        ],
        "leftovers": [],
        "constraints": {"attendees": 2, "time_window": "evening"},
        "planner_options": {"recipe_search_enabled": False, "recipe_search_keywords": []},
    }


@pytest.fixture()
def sample_plan() -> Plan:
    """Construct a deterministic plan object for dependency overrides."""

    candidate = PlanCandidate(
        title="Mock Dish",
        estimated_time_min=25,
        servings=2,
        steps=["Do mock prep", "Cook mock dish"],
        ingredients_required=[
            IngredientRequirement(ingredient_id=101, name="tofu", quantity_g=200.0)
        ],
        inventory_deltas=[InventoryDelta(ingredient_id=101, use_g=200.0)],
        shopping_shortfall=[
            ShoppingShortfall(name="green onions", need_count=2, reason="not_in_inventory")
        ],
        macros_per_serving=None,
    )
    return Plan(date=date.today(), candidates=[candidate])
@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Ensure each test uses an isolated SQLite database location."""

    db_path = tmp_path / "test_remy.db"
    monkeypatch.setenv("REMY_DATABASE_PATH", str(db_path))
    get_settings.cache_clear()
    reset_repository_state()
    yield
    reset_repository_state()
    monkeypatch.delenv("REMY_DATABASE_PATH", raising=False)
    get_settings.cache_clear()
