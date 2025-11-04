"""LLM runtime abstraction layer."""

from __future__ import annotations

from typing import Protocol


class PlannerLLM(Protocol):
    """Protocol for planner language model backends."""

    def generate(self, prompt: str, *, max_tokens: int | None = None) -> str:
        """Return generated text for the supplied prompt."""


class MockPlannerLLM:
    """Simple deterministic LLM stub for development."""

    def generate(self, prompt: str, *, max_tokens: int | None = None) -> str:
        return '{"candidates": []}'
