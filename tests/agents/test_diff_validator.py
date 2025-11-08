"""Tests for the Diff & Validator agent."""

from __future__ import annotations

from datetime import date

from remy.agents.diff_validator import DiffValidator
from remy.models.context import Constraints, InventoryItem, PlanningContext, Preferences
from remy.models.plan import (
    IngredientRequirement,
    Plan,
    PlanCandidate,
)


def build_context():
    return PlanningContext(
        date=date.today(),
        prefs=Preferences(diet="omnivore"),
        inventory=[
            InventoryItem(id=1, name="Chicken Thigh", qty=500, unit="g"),
            InventoryItem(id=2, name="Vegetable Broth", qty=1, unit="l"),
        ],
        leftovers=[],
        constraints=Constraints(attendees=2, time_window="evening"),
    )


def build_plan():
    candidate = PlanCandidate(
        title="Braised Chicken",
        estimated_time_min=40,
        servings=2,
        steps=[],
        ingredients_required=[
            IngredientRequirement(ingredient_id=1, name="Chicken Thigh", qty_g=600),
            IngredientRequirement(name="Vegetable Broth", qty_ml=250),
            IngredientRequirement(name="Lemon", qty_count=2),
        ],
    )
    return Plan(date=date.today(), candidates=[candidate])


def build_imperial_context():
    return PlanningContext(
        date=date.today(),
        prefs=Preferences(diet="omnivore"),
        inventory=[
            InventoryItem(id=10, name="Ground Beef", qty=2.0, unit="lb"),
        ],
        leftovers=[],
        constraints=Constraints(attendees=2, time_window="evening"),
    )


def test_diff_validator_aligns_inventory_deltas():
    validator = DiffValidator()
    context = build_context()
    plan = build_plan()

    normalized = validator.run((context, plan))
    candidate = normalized.candidates[0]

    assert len(candidate.inventory_deltas) == 2
    delta_by_id = {delta.ingredient_id: delta for delta in candidate.inventory_deltas}
    assert abs(delta_by_id[1].use_g - 500) < 1e-6
    assert abs(delta_by_id[2].use_ml - 250) < 1e-6

    assert len(candidate.shopping_shortfall) == 2
    shortfall_reasons = {short.name: short.reason for short in candidate.shopping_shortfall}
    assert shortfall_reasons["Chicken Thigh"] == "insufficient_stock"
    assert shortfall_reasons["Lemon"] == "not_in_inventory"


def test_diff_validator_estimates_macros_and_diagnostics():
    validator = DiffValidator()
    context = build_context()
    plan = build_plan()

    normalized = validator.run((context, plan))
    candidate = normalized.candidates[0]

    assert candidate.macros_per_serving is not None
    assert candidate.diagnostics
    assert any("macros" in note.lower() for note in candidate.diagnostics)


def test_diff_validator_handles_imperial_units():
    validator = DiffValidator()
    context = build_imperial_context()
    plan = Plan(
        date=date.today(),
        candidates=[
            PlanCandidate(
                title="Smash Burgers",
                servings=2,
                ingredients_required=[
                    IngredientRequirement(ingredient_id=10, name="Ground Beef", qty_g=600),
                ],
            )
        ],
    )

    normalized = validator.run((context, plan))
    candidate = normalized.candidates[0]
    assert candidate.shopping_shortfall == []
    assert candidate.inventory_deltas
    assert abs(candidate.inventory_deltas[0].use_g - 600) < 1e-6
