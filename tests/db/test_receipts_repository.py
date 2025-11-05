"""Tests for receipt repository helpers."""

from __future__ import annotations

import pytest

from remy.config import get_settings
from remy.db.receipts import (
    claim_receipts_for_ocr,
    delete_receipt,
    fetch_receipt,
    fetch_receipt_blob,
    get_receipt_ocr,
    list_receipts,
    store_receipt,
    update_receipt_ocr,
)
from remy.db.repository import reset_repository_state


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "receipts.db"
    monkeypatch.setenv("REMY_DATABASE_PATH", str(db_path))
    get_settings.cache_clear()
    reset_repository_state()
    yield
    reset_repository_state()
    monkeypatch.delenv("REMY_DATABASE_PATH", raising=False)
    get_settings.cache_clear()


def test_store_and_list_receipts(isolated_db):
    receipt = store_receipt(
        filename="receipt.txt",
        content_type="text/plain",
        content=b"hello world",
        notes="groceries",
    )
    assert receipt.id is not None
    assert receipt.size_bytes == 11
    assert receipt.notes == "groceries"

    receipts = list_receipts()
    assert len(receipts) == 1
    assert receipts[0].filename == "receipt.txt"
    ocr_status = get_receipt_ocr(receipt.id)
    assert ocr_status.status == "pending"
    assert ocr_status.text is None


def test_fetch_and_delete_receipt(isolated_db):
    saved = store_receipt(
        filename="receipt.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4",
    )

    fetched = fetch_receipt(saved.id)
    assert fetched.filename == "receipt.pdf"

    metadata, blob = fetch_receipt_blob(saved.id)
    assert metadata.id == saved.id
    assert blob.startswith(b"%PDF")

    status = update_receipt_ocr(
        saved.id,
        status="succeeded",
        text="Milk 1L",
        confidence=0.95,
        metadata={"word_count": 2},
    )
    assert status.text == "Milk 1L"
    assert status.metadata == {"word_count": 2}

    delete_receipt(saved.id)

    with pytest.raises(ValueError):
        get_receipt_ocr(saved.id)

    receipts = list_receipts()
    assert receipts == []


def test_claim_receipts_for_ocr(isolated_db):
    first = store_receipt(
        filename="one.png",
        content_type="image/png",
        content=b"\x89PNG\r\n\x1a\n",
    )
    second = store_receipt(
        filename="two.png",
        content_type="image/png",
        content=b"\x89PNG\r\n\x1a\n",
    )

    first_claim = claim_receipts_for_ocr(limit=1)
    assert first.id in first_claim
    assert get_receipt_ocr(first.id).status == "processing"

    second_claim = claim_receipts_for_ocr(limit=5)
    assert second.id in second_claim

    update_receipt_ocr(first.id, status="failed")
    retry_claim = claim_receipts_for_ocr(limit=5)
    assert first.id in retry_claim
