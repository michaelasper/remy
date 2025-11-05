"""Receipt ingestor agent."""

from __future__ import annotations

from typing import Iterable, List

from remy.agents.base import Agent
from remy.config import get_settings
from remy.models.receipt import ReceiptOcrResult
from remy.ocr import ReceiptOcrService


class ReceiptIngestor(Agent[Iterable[int], List[ReceiptOcrResult]]):
    """Process receipts via OCR and return extraction results."""

    def __init__(self, ocr_service: ReceiptOcrService | None = None) -> None:
        self._ocr_service = ocr_service or ReceiptOcrService(
            lang=get_settings().ocr_default_lang
        )

    def run(self, payload: Iterable[int]) -> List[ReceiptOcrResult]:
        results: List[ReceiptOcrResult] = []
        for receipt_id in payload:
            results.append(self._ocr_service.process_receipt(receipt_id))
        return results
