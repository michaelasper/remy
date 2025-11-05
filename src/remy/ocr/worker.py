"""Background worker that processes staged receipts via OCR."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, List, Optional

from remy.db.receipts import claim_receipts_for_ocr, offload_receipt_content
from remy.ocr.pipeline import ReceiptOcrService

logger = logging.getLogger(__name__)


class ReceiptOcrWorker:
    """Poll the database for pending receipts and run OCR sequentially."""

    def __init__(
        self,
        *,
        service: Optional[ReceiptOcrService] = None,
        claimer: Callable[[int], List[int]] = claim_receipts_for_ocr,
        poll_interval: float = 5.0,
        batch_size: int = 5,
        archive_dir: Optional[Path] = None,
    ) -> None:
        self._service = service or ReceiptOcrService()
        self._claimer = claimer
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._archive_dir = archive_dir
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Spawn the worker loop in a daemon thread."""

        if self._thread and self._thread.is_alive():
            logger.debug("OCR worker already running")
            return
        logger.info(
            "Starting OCR worker poll_interval=%s batch_size=%s",
            self._poll_interval,
            self._batch_size,
        )
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="receipt-ocr-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the worker loop to exit and wait briefly for shutdown."""

        if not self._thread:
            return
        logger.info("Stopping OCR worker")
        self._stop_event.set()
        self._thread.join(timeout=self._poll_interval + 1)
        self._thread = None

    def poll_once(self) -> int:
        """Process a single batch of receipts and return the count handled."""

        receipt_ids = self._claimer(self._batch_size)
        processed = 0
        for receipt_id in receipt_ids:
            try:
                result = self._service.process_receipt(receipt_id)
                if (
                    self._archive_dir is not None
                    and result.status == "succeeded"
                ):
                    try:
                        offload_receipt_content(receipt_id, archive_dir=self._archive_dir)
                    except Exception:  # pragma: no cover - best-effort archival
                        logger.exception(
                            "Unable to archive receipt %s after OCR", receipt_id
                        )
                processed += 1
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("OCR processing failed for receipt_id=%s", receipt_id)
        return processed

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            processed = self.poll_once()
            if processed == 0:
                if self._stop_event.wait(self._poll_interval):
                    break


__all__ = ["ReceiptOcrWorker"]
