"""Common agent interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class Agent(ABC, Generic[InputT, OutputT]):
    """Base agent interface implemented by all Remy agents."""

    @abstractmethod
    def run(self, payload: InputT) -> OutputT:
        """Execute the agent with the given payload."""
