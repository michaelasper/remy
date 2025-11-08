"""Helpers for assembling the planning context from persisted data."""

from __future__ import annotations

from datetime import date
from typing import Optional

from remy.db.inventory import list_inventory
from remy.db.meals import list_recent_meals
from remy.db.preferences import load_preferences
from remy.models.context import Constraints, PlanningContext


def assemble_planning_context(
    *,
    target_date: date,
    attendees: Optional[int] = None,
    time_window: Optional[str] = None,
    recent_meal_limit: int = 14,
) -> PlanningContext:
    """Return a fully-hydrated PlanningContext for the supplied parameters."""

    prefs = load_preferences()
    recent_meals = list_recent_meals(limit=max(1, recent_meal_limit))
    inventory = list_inventory()

    constraints = Constraints(attendees=attendees, time_window=time_window)

    return PlanningContext(
        date=target_date,
        prefs=prefs,
        recent_meals=recent_meals,
        inventory=inventory,
        leftovers=[],  # TODO: populate when leftover tracking lands
        constraints=constraints,
    )
