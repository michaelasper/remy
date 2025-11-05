"""Heuristic planner tests."""

from __future__ import annotations

from datetime import date, timedelta

from remy.models.context import (
    Constraints,
    InventoryItem,
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
