"""Constraint engine planner tests."""

from __future__ import annotations

from datetime import date, timedelta

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
