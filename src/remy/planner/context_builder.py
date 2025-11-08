"""Helpers for assembling the planning context from persisted data."""

from __future__ import annotations

from datetime import date
from typing import Optional

from remy.config import get_settings
from remy.db.inventory import list_inventory
from remy.db.leftovers import list_leftovers
from remy.db.meals import list_recent_meals
from remy.db.preferences import load_preferences
from remy.models.context import Constraints, PlannerOptions, PlanningContext


def assemble_planning_context(
    *,
    target_date: date,
    attendees: Optional[int] = None,
    time_window: Optional[str] = None,
    recent_meal_limit: int = 14,
    diet_override: Optional[str] = None,
    allergens_override: Optional[list[str]] = None,
    max_time_override: Optional[int] = None,
    preferred_cuisines: Optional[list[str]] = None,
    recipe_search_enabled: Optional[bool] = None,
    recipe_search_keywords: Optional[list[str]] = None,
) -> PlanningContext:
    """Return a fully-hydrated PlanningContext for the supplied parameters."""

    settings = get_settings()
    prefs = load_preferences()
    override_data: dict[str, object] = {}
    if diet_override:
        override_data["diet"] = diet_override
    if max_time_override is not None:
        override_data["max_time_min"] = max_time_override
    if allergens_override is not None:
        normalized_allergens = [value.strip() for value in allergens_override if value.strip()]
        override_data["allergens"] = normalized_allergens
    if override_data:
        prefs = prefs.model_copy(update=override_data)
    recent_meals = list_recent_meals(limit=max(1, recent_meal_limit))
    inventory = list_inventory()
    leftovers = list_leftovers()

    normalized_cuisines = [value.strip() for value in (preferred_cuisines or []) if value.strip()]
    constraints = Constraints(
        attendees=attendees,
        time_window=time_window,
        preferred_cuisines=normalized_cuisines,
    )
    normalized_keywords = [value.strip() for value in (recipe_search_keywords or []) if value.strip()]
    options = PlannerOptions(
        recipe_search_enabled=(
            recipe_search_enabled
            if recipe_search_enabled is not None
            else settings.planner_enable_recipe_search
        ),
        recipe_search_keywords=normalized_keywords,
    )

    return PlanningContext(
        date=target_date,
        prefs=prefs,
        recent_meals=recent_meals,
        inventory=inventory,
        leftovers=leftovers,
        constraints=constraints,
        planner_options=options,
    )
