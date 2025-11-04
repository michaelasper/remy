"""Notification agent."""

from __future__ import annotations

from remy.agents.base import Agent
from remy.models.plan import Plan


class Notifier(Agent[Plan, Plan]):
    """Send plan notifications to household members."""

    def run(self, payload: Plan) -> Plan:
        # TODO: deliver notifications via Home Assistant or other channels.
        return payload
