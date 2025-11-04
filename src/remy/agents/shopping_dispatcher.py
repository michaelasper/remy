"""Shopping dispatcher agent."""

from __future__ import annotations

from remy.agents.base import Agent
from remy.models.plan import ShoppingShortfall


class ShoppingDispatcher(Agent[list[ShoppingShortfall], list[ShoppingShortfall]]):
    """Send shopping shortfalls to third-party services such as Home Assistant."""

    def run(self, payload: list[ShoppingShortfall]) -> list[ShoppingShortfall]:
        # TODO: integrate with Home Assistant or other shopping providers.
        return payload
