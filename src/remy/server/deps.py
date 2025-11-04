"""Dependency definitions for the Remy API server."""

from __future__ import annotations

from typing import Callable

from remy.models.context import PlanningContext
from remy.models.plan import Plan
from remy.planner.app.planner import generate_plan

PlanGenerator = Callable[[PlanningContext], Plan]


def get_plan_generator() -> PlanGenerator:
    """Return the default plan generator implementation."""

    return generate_plan
