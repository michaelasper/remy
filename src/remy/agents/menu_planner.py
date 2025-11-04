"""Menu planner agent."""

from __future__ import annotations

from remy.agents.base import Agent
from remy.models.context import PlanningContext
from remy.models.plan import Plan
from remy.planner.app.planner import generate_plan


class MenuPlanner(Agent[PlanningContext, Plan]):
    """Generate candidate dinner plans from the assembled context."""

    def run(self, payload: PlanningContext) -> Plan:
        """Return preliminary plan candidates."""
        return generate_plan(payload)
