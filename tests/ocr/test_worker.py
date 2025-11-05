"""Tests for the OCR worker loop."""

from __future__ import annotations

from remy.ocr.worker import ReceiptOcrWorker


class DummyService:
    def __init__(self) -> None:
        self.processed: list[int] = []

    def process_receipt(self, receipt_id: int) -> None:
        self.processed.append(receipt_id)


def test_worker_poll_once_processes_receipts():
    service = DummyService()
    worker = ReceiptOcrWorker(
        service=service,
        claimer=lambda limit: [1, 2][:limit],
        poll_interval=0.01,
        batch_size=2,
    )

    processed_count = worker.poll_once()

    assert processed_count == 2
    assert service.processed == [1, 2]
