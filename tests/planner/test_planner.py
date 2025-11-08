"""Constraint engine planner tests."""

from __future__ import annotations

import json
from datetime import date, timedelta

import httpx

from remy.config import get_settings
from remy.models.context import (
    Constraints,
    InventoryItem,
    LeftoverItem,
    PlanningContext,
    Preferences,
)
from remy.models.plan import PlanCandidate
from remy.planner.app.planner import generate_plan


def _inventory_item(**kwargs) -> InventoryItem:
    defaults = {
        "id": 1,
        "name": "chicken thigh, boneless",
        "qty": 600,
        "unit": "g",
        "best_before": date.today() + timedelta(days=2),
    }
    defaults.update(kwargs)
    return InventoryItem.model_validate(defaults)


def _leftover_item(**kwargs) -> LeftoverItem:
    defaults = {
        "name": "tofu",
        "qty": 200,
        "unit": "g",
    }
    defaults.update(kwargs)
    return LeftoverItem.model_validate(defaults)


def test_planner_prioritises_near_expiry_inventory():
    inventory = [
        _inventory_item(
            id=1,
            name="chicken thigh, boneless",
            qty=800,
            best_before=date.today(),
        ),
        _inventory_item(
            id=2,
            name="broccoli",
            qty=400,
            unit="g",
            best_before=date.today() + timedelta(days=1),
        ),
    ]
    context = PlanningContext(
        date=date.today(),
        inventory=inventory,
        prefs=Preferences(diet="omnivore", max_time_min=45, allergens=[]),
        constraints=Constraints(attendees=2, time_window="evening"),
    )

    plan = generate_plan(context)
    assert len(plan.candidates) >= 1
    assert any("chicken" in candidate.title.lower() for candidate in plan.candidates)


def test_planner_filters_allergens_and_respects_time():
    inventory = [
        _inventory_item(
            id=3,
            name="salmon fillet",
            qty=500,
            best_before=date.today() + timedelta(days=3),
        ),
        _inventory_item(
            id=4,
            name="mixed greens",
            qty=200,
            unit="g",
            best_before=date.today() + timedelta(days=5),
        ),
    ]
    context = PlanningContext(
        date=date.today(),
        inventory=inventory,
        prefs=Preferences(diet="pescatarian", max_time_min=30, allergens=["almonds"]),
        constraints=Constraints(attendees=2, time_window="evening"),
    )

    plan = generate_plan(context)

    assert all(isinstance(candidate, PlanCandidate) for candidate in plan.candidates)
    # ensure allergen-bearing recipes are removed
    for candidate in plan.candidates:
        assert "almond" not in " ".join(step.lower() for step in candidate.steps)


def test_optional_ingredient_missing_does_not_raise_shortfall():
    inventory = [
        _inventory_item(
            id=5,
            name="chicken thigh, boneless",
            qty=600,
            best_before=date.today() + timedelta(days=1),
        ),
        _inventory_item(
            id=6,
            name="broccoli",
            qty=400,
            unit="g",
            best_before=date.today() + timedelta(days=2),
        ),
    ]
    context = PlanningContext(
        date=date.today(),
        inventory=inventory,
        prefs=Preferences(diet="omnivore", max_time_min=60, allergens=[]),
        constraints=Constraints(attendees=4),
    )

    plan = generate_plan(context)
    chicken_candidates = [
        candidate for candidate in plan.candidates if "lemon herb chicken" in candidate.title.lower()
    ]
    assert chicken_candidates
    for candidate in chicken_candidates:
        assert all(shortfall.name.lower() != "lemon" for shortfall in candidate.shopping_shortfall)


def test_leftovers_are_prioritised_when_available():
    inventory = [
        _inventory_item(id=7, name="bell pepper", qty=280, unit="g"),
        _inventory_item(id=8, name="carrot", qty=200, unit="g"),
        _inventory_item(id=9, name="soy sauce", qty=100, unit="ml"),
        _inventory_item(id=10, name="garlic", qty=30, unit="g"),
    ]
    leftovers = [
        _leftover_item(name="tofu", qty=250, unit="g"),
    ]
    context = PlanningContext(
        date=date.today(),
        inventory=inventory,
        leftovers=leftovers,
        prefs=Preferences(diet="vegan", max_time_min=45, allergens=[]),
        constraints=Constraints(attendees=2),
    )

    plan = generate_plan(context)
    assert plan.candidates
    assert plan.candidates[0].title == "Vegetable Stir-Fry with Tofu"


def test_generate_plan_uses_openai_llm_when_available(monkeypatch):
    monkeypatch.setenv("REMY_LLM_PROVIDER", "openai")
    monkeypatch.setenv("REMY_LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("REMY_LLM_MODEL", "test-model")
    get_settings.cache_clear()

    captured = {}

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class DummyClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            captured["url"] = url
            captured["payload"] = json
            plan_payload = {
                "date": str(date.today()),
                "candidates": [
                    {
                        "title": "LLM Curry",
                        "estimated_time_min": 30,
                        "servings": 2,
                        "steps": ["one", "two"],
                        "ingredients_required": [],
                        "inventory_deltas": [],
                        "shopping_shortfall": [],
                        "macros_per_serving": None,
                    }
                ],
            }
            content = json_module.dumps(plan_payload)
            return DummyResponse({"choices": [{"message": {"content": content}}]})

    json_module = json  # alias to avoid shadowing in DummyClient.post signature
    monkeypatch.setattr("remy.planner.app.planner.httpx.Client", DummyClient)

    context = PlanningContext(
        date=date.today(),
        inventory=[_inventory_item()],
        prefs=Preferences(diet="vegan", max_time_min=30, allergens=[]),
        constraints=Constraints(attendees=2),
    )

    plan = generate_plan(context)

    assert plan.candidates[0].title == "LLM Curry"
    assert captured["url"].endswith("/chat/completions")
    assert captured["payload"]["model"] == "test-model"


def test_generate_plan_falls_back_when_llm_errors(monkeypatch):
    monkeypatch.setenv("REMY_LLM_PROVIDER", "openai")
    monkeypatch.setenv("REMY_LLM_BASE_URL", "http://llm.test/v1")
    get_settings.cache_clear()

    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            raise httpx.HTTPError("boom")

    monkeypatch.setattr("remy.planner.app.planner.httpx.Client", FailingClient)

    context = PlanningContext(
        date=date.today(),
        inventory=[_inventory_item()],
        prefs=Preferences(diet="omnivore", max_time_min=45, allergens=[]),
        constraints=Constraints(attendees=2),
    )

    plan = generate_plan(context)
    assert plan.candidates  # Fallback still produces a plan


def test_generate_plan_uses_ollama_provider(monkeypatch):
    monkeypatch.setenv("REMY_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("REMY_LLM_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("REMY_LLM_MODEL", "test-ollama")
    get_settings.cache_clear()

    captured = {}

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class DummyClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            captured["url"] = url
            captured["payload"] = json
            plan_payload = {
                "date": str(date.today()),
                "candidates": [
                    {
                        "title": "Ollama Tofu",
                        "estimated_time_min": 20,
                        "servings": 2,
                        "steps": ["prep", "cook"],
                        "ingredients_required": [],
                        "inventory_deltas": [],
                        "shopping_shortfall": [],
                        "macros_per_serving": None,
                    }
                ],
            }
            content = json_module.dumps(plan_payload)
            response_payload = {
                "model": "test-ollama",
                "message": {"role": "assistant", "content": content},
                "done": True,
            }
            return DummyResponse(response_payload)

    json_module = json
    monkeypatch.setattr("remy.planner.app.planner.httpx.Client", DummyClient)

    context = PlanningContext(
        date=date.today(),
        inventory=[_inventory_item()],
        prefs=Preferences(diet="vegan", max_time_min=30, allergens=[]),
        constraints=Constraints(attendees=2),
    )

    plan = generate_plan(context)

    assert plan.candidates[0].title == "Ollama Tofu"
    assert captured["url"].endswith("/api/chat")
    assert captured["payload"]["model"] == "test-ollama"
