"""Receipt OCR pipeline implementation using Tesseract."""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from pdf2image import convert_from_bytes
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

try:  # pragma: no cover - import guarded for environments without pytesseract
    import pytesseract
    from pytesseract import Output
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore[assignment]
    Output = None  # type: ignore[assignment]

from remy import metrics
from remy.db.receipts import fetch_receipt_blob, get_receipt_ocr, update_receipt_ocr
from remy.ingest import ingest_receipt_items
from remy.models.receipt import Receipt, ReceiptOcrResult
from remy.ocr.parser import ReceiptParser
from remy.ocr.sanitize import sanitize_text

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/bmp",
    "image/tiff",
}


class UnsupportedReceiptError(RuntimeError):
    """Raised when a receipt cannot be processed by the OCR engine."""


@dataclass
class OcrContext:
    receipt: Receipt
    images: List[Image.Image]


class ReceiptOcrService:
    """Synchronous OCR processing pipeline for stored receipts."""

    def __init__(
        self,
        *,
        receipt_fetcher: Callable[[int], tuple[Receipt, bytes]] = fetch_receipt_blob,
        status_getter: Callable[[int], Optional[ReceiptOcrResult]] = get_receipt_ocr,
        status_updater: Callable[..., ReceiptOcrResult] = update_receipt_ocr,
        lang: str | None = None,
        parser: Optional[ReceiptParser] = None,
    ) -> None:
        self._fetch_receipt = receipt_fetcher
        self._get_status = status_getter
        self._update_status = status_updater
        if lang is None:
            try:
                from remy.config import get_settings

                lang = get_settings().ocr_default_lang
            except Exception:  # pragma: no cover - fallback if settings unavailable
                lang = "eng"
        self._lang = lang
        self._parser = parser or ReceiptParser()

    def get_status(self, receipt_id: int) -> Optional[ReceiptOcrResult]:
        """Return the current OCR status for a receipt, if recorded."""

        return self._get_status(receipt_id)

    def process_receipt(self, receipt_id: int) -> ReceiptOcrResult:
        """Run OCR against the requested receipt and persist the result."""

        logger.debug("Starting OCR processing for receipt_id=%s", receipt_id)
        existing_status = self._get_status(receipt_id)
        auto_ingest_allowed = True
        if existing_status and existing_status.metadata:
            auto_ingest_allowed = not existing_status.metadata.get("auto_ingested")

        try:
            context = self._prepare_context(receipt_id)
            self._update_status(receipt_id, status="processing")
            text, confidence, metadata = self._run_ocr(
                context, auto_ingest=auto_ingest_allowed
            )
            result = self._update_status(
                receipt_id,
                status="succeeded",
                text=text,
                confidence=confidence,
                metadata=metadata,
                error_message=None,
            )
            metrics.OCR_JOBS.labels(status="succeeded").inc()
            logger.debug(
                "OCR succeeded receipt_id=%s confidence=%s", receipt_id, result.confidence
            )
            return result
        except UnsupportedReceiptError as exc:
            logger.warning(
                "Unsupported receipt for OCR receipt_id=%s reason=%s", receipt_id, exc
            )
            metrics.OCR_JOBS.labels(status="unsupported").inc()
            return self._update_status(
                receipt_id,
                status="failed",
                error_message=str(exc),
                metadata={"reason": "unsupported"},
            )
        except ValueError:
            # Propagate canonical "not found" errors to HTTP layer.
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("OCR pipeline crash receipt_id=%s", receipt_id)
            metrics.OCR_JOBS.labels(status="failed").inc()
            return self._update_status(
                receipt_id,
                status="failed",
                error_message=str(exc),
            )

    def _prepare_context(self, receipt_id: int) -> OcrContext:
        receipt, blob = self._fetch_receipt(receipt_id)
        if pytesseract is None:  # pragma: no cover - guard for missing dependency
            raise UnsupportedReceiptError(
                "pytesseract is not installed. Install OCR extras to enable processing."
            )
        images = self._load_images(receipt, blob, receipt_id)
        if not images:
            raise UnsupportedReceiptError("Receipt does not contain any decodable pages.")
        return OcrContext(receipt=receipt, images=images)

    @staticmethod
    def _is_supported_content_type(content_type: str) -> bool:
        normalized = content_type.lower()
        return normalized in SUPPORTED_IMAGE_TYPES

    def _load_images(
        self, receipt: Receipt, blob: bytes, receipt_id: int
    ) -> List[Image.Image]:
        content_type = (receipt.content_type or "").lower()
        if content_type == "application/pdf" or receipt.filename.lower().endswith(".pdf"):
            try:
                pages = convert_from_bytes(blob, fmt="png")
            except Exception as exc:
                raise UnsupportedReceiptError(
                    "Unable to convert PDF for OCR. Ensure poppler utilities are installed."
                ) from exc
            return pages

        if content_type and self._is_supported_content_type(content_type):
            try:
                return [Image.open(io.BytesIO(blob))]
            except UnidentifiedImageError as exc:
                raise UnsupportedReceiptError(
                    f"Unable to decode image content type {receipt.content_type}"
                ) from exc

        # Attempt best-effort decoding when content type missing or generic.
        try:
            return [Image.open(io.BytesIO(blob))]
        except UnidentifiedImageError as exc:
            raise UnsupportedReceiptError(
                f"Receipt {receipt_id} is not an image format supported by OCR."
            ) from exc

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        processed = ImageOps.grayscale(image)
        processed = ImageOps.autocontrast(processed)
        processed = processed.filter(ImageFilter.MedianFilter(size=3))

        if pytesseract is not None:
            try:
                osd = pytesseract.image_to_osd(processed, lang=self._lang)
                rotation = self._parse_rotation_from_osd(osd)
                if rotation:
                    processed = processed.rotate(-rotation, expand=True, fillcolor=255)
            except Exception:  # pragma: no cover - orientation detection best effort
                pass
        return processed

    @staticmethod
    def _parse_rotation_from_osd(osd: str) -> int:
        match = re.search(r"Rotate: (\d+)", osd)
        if not match:
            return 0
        try:
            value = int(match.group(1)) % 360
        except ValueError:
            return 0
        return value

    def _run_ocr(
        self, context: OcrContext, *, auto_ingest: bool
    ) -> tuple[str, Optional[float], Dict[str, object]]:
        if pytesseract is None or Output is None:  # pragma: no cover - guard
            raise UnsupportedReceiptError(
                "pytesseract is not installed. Install OCR extras to enable processing."
            )

        page_texts: List[str] = []
        page_confidences: List[float] = []
        page_metadata: List[dict[str, object]] = []
        words_summary: List[dict[str, object]] = []

        for page_number, raw_image in enumerate(context.images, start=1):
            processed = self._preprocess_image(raw_image)
            text, confidence, words = self._run_ocr_page(processed)
            page_texts.append(text)
            if confidence is not None:
                page_confidences.append(confidence)
            page_metadata.append(
                {
                    "page": page_number,
                    "word_count": sum(1 for word in words if word["text"]),
                    "confidence": confidence,
                    "image_size": {"width": processed.width, "height": processed.height},
                }
            )
            words_summary.extend(
                {
                    "page": page_number,
                    "text": word["text"],
                    "confidence": word["confidence"],
                    "left": word["left"],
                    "top": word["top"],
                    "width": word["width"],
                    "height": word["height"],
                }
                for word in words
                if word["text"]
            )

        text_output = "\n\n".join(entry.strip() for entry in page_texts if entry.strip())
        text_output = sanitize_text(text_output)
        average_confidence = None
        if page_confidences:
            average_confidence = sum(page_confidences) / len(page_confidences)

        metadata: Dict[str, object] = {
            "lang": self._lang,
            "pages": page_metadata,
            "word_count": sum(entry["word_count"] for entry in page_metadata),
            "mean_confidence_raw": (
                average_confidence * 100 if average_confidence is not None else None
            ),
        }
        if words_summary:
            metadata["words"] = words_summary[:1000]

        if self._parser and text_output:
            parsed = self._parser.parse(text_output)
            parsed_payload = parsed.model_dump()
            metadata["parsed"] = parsed_payload
            ingestion_items = [
                {
                    "name": entry.get("name"),
                    "quantity": entry.get("quantity"),
                    "unit": entry.get("unit"),
                    "inventory_match_id": entry.get("inventory_match_id"),
                    "notes": entry.get("notes"),
                }
                for entry in parsed_payload.get("items", [])
            ]
            if auto_ingest and ingestion_items:
                ingestion_result = ingest_receipt_items(
                    context.receipt.id,
                    ingestion_items,
                    create_missing=True,
                )
                metadata["ingested"] = ingestion_result["metadata_ingested"]
                metadata["suggestions"] = ingestion_result["metadata_suggestions"]
                metadata["auto_ingested"] = True
            else:
                metadata.setdefault("ingested", [])
                metadata.setdefault("suggestions", [])

        return text_output, average_confidence, metadata

    def _run_ocr_page(
        self, image: Image.Image
    ) -> tuple[str, Optional[float], List[dict[str, object]]]:
        text = sanitize_text(pytesseract.image_to_string(image, lang=self._lang).strip())
        data = pytesseract.image_to_data(image, lang=self._lang, output_type=Output.DICT)

        confidences: List[float] = []
        words: List[dict[str, object]] = []
        texts = data.get("text", [])
        confs = data.get("conf", [])
        lefts = data.get("left", [])
        tops = data.get("top", [])
        widths = data.get("width", [])
        heights = data.get("height", [])

        def _safe_int(value: object) -> Optional[int]:
            try:
                return int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None

        for idx, raw_text in enumerate(texts):
            normalized_text = sanitize_text((raw_text or "").strip())
            raw_conf = confs[idx] if idx < len(confs) else ""
            try:
                confidence = float(raw_conf)
            except (TypeError, ValueError):
                confidence = -1.0
            if confidence >= 0:
                confidences.append(confidence / 100.0)
            words.append(
                {
                    "text": normalized_text,
                    "confidence": confidence / 100.0 if confidence >= 0 else None,
                    "left": _safe_int(lefts[idx] if idx < len(lefts) else None),
                    "top": _safe_int(tops[idx] if idx < len(tops) else None),
                    "width": _safe_int(widths[idx] if idx < len(widths) else None),
                    "height": _safe_int(heights[idx] if idx < len(heights) else None),
                }
            )

        avg_confidence = None
        if confidences:
            avg_confidence = sum(confidences) / len(confidences)

        return text, avg_confidence, words
