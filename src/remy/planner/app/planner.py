"""Planner implementation entry point."""

from __future__ import annotations

from typing import List

from remy.models.context import InventoryItem, PlanningContext
from remy.models.plan import IngredientRequirement, InventoryDelta, Plan, PlanCandidate

PLACEHOLDER_STEPS = [
    "Review pantry inventory and select ingredients to prioritize.",
    "Prepare ingredients as needed (e.g., chop vegetables, preheat oven).",
    "Cook and plate the meal.",
]


def _build_placeholder_candidate(
    inventory_item: InventoryItem,
    context: PlanningContext,
) -> PlanCandidate:
    """Create a simple placeholder candidate that exercises the data model."""
    use_amount = min(inventory_item.quantity, 250.0)
    servings = context.constraints.attendees or 2
    estimated_time = context.prefs.max_time_min or 30

    return PlanCandidate(
        title=f"Quick {inventory_item.name.title()}",
        estimated_time_min=estimated_time,
        servings=servings,
        steps=list(PLACEHOLDER_STEPS),
        ingredients_required=[
            IngredientRequirement(
                ingredient_id=inventory_item.id,
                name=inventory_item.name,
                quantity_g=use_amount,
            )
        ],
        inventory_deltas=[InventoryDelta(ingredient_id=inventory_item.id, use_g=use_amount)],
        shopping_shortfall=[],
        macros_per_serving=None,
    )


def generate_plan(context: PlanningContext) -> Plan:
    """
    Generate dinner candidates for the provided context.

    The current scaffold returns a placeholder candidate that uses the first inventory item,
    ensuring the pipeline functions end-to-end during early development.
    """
    candidates: List[PlanCandidate] = []

    if context.inventory:
        candidates.append(_build_placeholder_candidate(context.inventory[0], context))

    return Plan(date=context.date, candidates=candidates)
