"""Tests for the OCR pipeline service."""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from PIL import Image

from remy.db.receipts import get_receipt_ocr, store_receipt
from remy.models.receipt import ReceiptStructuredData
from remy.ocr.pipeline import ReceiptOcrService


def _create_image_bytes() -> bytes:
    image = Image.new("RGB", (32, 32), color=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def stub_pytesseract(monkeypatch):
    from remy.ocr import pipeline

    class DummyPytesseract:
        @staticmethod
        def image_to_string(image, lang):
            return "milk 1l\ncard 4111 1111 1111 1111\nbread 2"

        @staticmethod
        def image_to_data(image, lang, output_type):
            assert output_type == "DICT"
            return {
                "text": ["milk", "1l", "card", "4111", "1111", "1111", "1111", "bread", "2"],
                "conf": ["90", "80", "70", "70", "70", "70", "70", "95", "85"],
                "left": [0, 40, 0, 35, 70, 105, 140, 0, 60],
                "top": [0, 0, 12, 12, 12, 12, 12, 20, 20],
                "width": [30, 20, 30, 30, 30, 30, 30, 35, 15],
                "height": [10, 10, 10, 10, 10, 10, 10, 12, 12],
            }

        @staticmethod
        def image_to_osd(image, lang):
            return "Rotate: 0"

    monkeypatch.setattr(pipeline, "pytesseract", DummyPytesseract())
    monkeypatch.setattr(pipeline, "Output", SimpleNamespace(DICT="DICT"))
    yield


def test_process_receipt_success(tmp_path):
    receipt = store_receipt(
        filename="receipt.png",
        content_type="image/png",
        content=_create_image_bytes(),
    )

    class DummyParser:
        def parse(self, text):
            return ReceiptStructuredData(items=[])

    service = ReceiptOcrService(parser=DummyParser())
    result = service.process_receipt(receipt.id)

    assert result.status == "succeeded"
    assert "milk" in result.text
    assert "****" in result.text
    assert "4111 1111 1111 1111" not in result.text
    assert result.confidence is not None
    assert result.metadata["word_count"] == len(result.metadata["words"])
    assert result.metadata["pages"][0]["word_count"] == len(result.metadata["words"])
    assert result.metadata.get("words")
    assert 70 <= result.metadata["mean_confidence_raw"] <= 100
    first_word = result.metadata["words"][0]
    assert first_word["left"] == 0
    assert "parsed" in result.metadata
    persisted = get_receipt_ocr(receipt.id)
    assert persisted.status == "succeeded"
    assert persisted.text == result.text


def test_process_receipt_unsupported_format():
    receipt = store_receipt(
        filename="receipt.txt",
        content_type="text/plain",
        content=b"not an image",
    )

    service = ReceiptOcrService()
    result = service.process_receipt(receipt.id)

    assert result.status == "failed"
    assert result.metadata.get("reason") == "unsupported"
    assert "not an image" in (result.error_message or "")
