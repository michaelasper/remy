"""Diff and validation agent."""

from __future__ import annotations

from remy.agents.base import Agent
from remy.models.context import PlanningContext
from remy.models.plan import Plan


class DiffValidator(Agent[tuple[PlanningContext, Plan], Plan]):
    """
    Normalize planner output, compute shortages, and validate schema compliance.

    The placeholder implementation returns the plan unchanged.
    """

    def run(self, payload: tuple[PlanningContext, Plan]) -> Plan:
        _context, plan = payload
        # TODO: implement normalization and diff computation using context data.
        return plan
