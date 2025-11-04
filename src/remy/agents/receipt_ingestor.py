"""Receipt ingestor agent."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from remy.agents.base import Agent


class ReceiptIngestor(Agent[Iterable[Path], list[Path]]):
    """Process receipts and update inventory records."""

    def run(self, payload: Iterable[Path]) -> list[Path]:
        # TODO: parse receipts and apply inventory updates.
        return list(payload)
