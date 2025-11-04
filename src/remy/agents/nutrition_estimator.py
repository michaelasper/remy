"""Nutrition estimator agent."""

from __future__ import annotations

from remy.agents.base import Agent
from remy.models.plan import Plan


class NutritionEstimator(Agent[Plan, Plan]):
    """Estimate macronutrients for each candidate."""

    def run(self, payload: Plan) -> Plan:
        # TODO: compute nutrition using ingredient quantities.
        return payload
