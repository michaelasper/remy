"""Approvals orchestration agent."""

from __future__ import annotations

from remy.agents.base import Agent
from remy.models.plan import Plan


class ApprovalsOrchestrator(Agent[Plan, Plan]):
    """
    Coordinate human approvals, persist selections, and trigger downstream actions.

    The current scaffold simply forwards the plan for development workflows.
    """

    def run(self, payload: Plan) -> Plan:
        # TODO: record approval state and persist results.
        return payload
