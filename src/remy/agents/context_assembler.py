"""Context assembler agent."""

from __future__ import annotations

from datetime import date

from remy.agents.base import Agent
from remy.models.context import PlanningContext


class ContextAssembler(Agent[None, PlanningContext]):
    """Build planning context from databases and external sources."""

    def run(self, payload: None = None) -> PlanningContext:
        """
        Assemble the planning context.

        The current implementation returns an empty scaffold for development and testing.
        """
        return PlanningContext(date=date.today())
