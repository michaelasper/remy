"""Dependency definitions for the Remy API server."""

from __future__ import annotations

from typing import Callable, List

from remy.db.inventory import load_inventory
from remy.models.context import InventoryItem, PlanningContext
from remy.models.plan import Plan
from remy.planner.app.planner import generate_plan

PlanGenerator = Callable[[PlanningContext], Plan]
InventoryProvider = Callable[[], List[InventoryItem]]


def get_plan_generator() -> PlanGenerator:
    """Return the default plan generator implementation."""

    return generate_plan


def get_inventory_provider() -> InventoryProvider:
    """Return the current inventory provider implementation."""

    return lambda: load_inventory()
