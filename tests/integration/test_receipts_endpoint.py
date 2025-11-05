"""Integration tests for receipt upload endpoints."""

from __future__ import annotations

from fastapi import status

from remy.db.receipts import update_receipt_ocr
from remy.server import deps


def test_receipt_upload_and_download_round_trip(client):
    files = {"file": ("receipt.txt", b"store receipt", "text/plain")}
    data = {"notes": "weekly groceries"}
    response = client.post("/receipts", files=files, data=data)
    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    receipt_id = payload["id"]
    assert payload["filename"] == "receipt.txt"
    assert payload["size_bytes"] == len("store receipt")
    assert payload["notes"] == "weekly groceries"

    list_response = client.get("/receipts")
    assert list_response.status_code == status.HTTP_200_OK
    items = list_response.json()
    assert any(item["id"] == receipt_id for item in items)

    meta_response = client.get(f"/receipts/{receipt_id}")
    assert meta_response.status_code == status.HTTP_200_OK
    assert meta_response.json()["filename"] == "receipt.txt"

    download_response = client.get(f"/receipts/{receipt_id}/download")
    assert download_response.status_code == status.HTTP_200_OK
    assert download_response.content == b"store receipt"
    assert download_response.headers["content-disposition"].startswith("attachment")


def test_receipt_upload_empty_file_rejected(client):
    files = {"file": ("empty.txt", b"", "text/plain")}
    response = client.post("/receipts", files=files)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "empty" in response.json()["detail"].lower()


def test_receipt_ocr_endpoints(client):
    files = {"file": ("receipt.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    upload_response = client.post("/receipts", files=files)
    receipt_id = upload_response.json()["id"]

    status_response = client.get(f"/receipts/{receipt_id}/ocr")
    assert status_response.status_code == status.HTTP_200_OK
    assert status_response.json()["status"] == "pending"

    def fake_processor(receipt_id: int):
        return update_receipt_ocr(
            receipt_id,
            status="succeeded",
            text="Milk 1L",
            confidence=0.9,
        )

    client.app.dependency_overrides[deps.get_receipt_ocr_processor] = lambda: fake_processor
    process_response = client.post(f"/receipts/{receipt_id}/ocr")
    assert process_response.status_code == status.HTTP_200_OK
    assert process_response.json()["status"] == "succeeded"
    client.app.dependency_overrides.pop(deps.get_receipt_ocr_processor, None)


def test_receipt_ingest_endpoint(client):
    files = {"file": ("ingest.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    upload_response = client.post("/receipts", files=files)
    receipt_id = upload_response.json()["id"]

    update_receipt_ocr(
        receipt_id,
        status="succeeded",
        text="Parsed",
        confidence=0.85,
        metadata={
            "parsed": {
                "items": [
                    {
                        "name": "Test Apples",
                        "quantity": 2.0,
                        "unit": "kg",
                        "confidence": 0.9,
                    }
                ]
            }
        },
    )

    ingest_response = client.post(
        f"/receipts/{receipt_id}/ingest",
        json={
            "items": [
                {"name": "Test Apples", "quantity": 2.0, "unit": "kg", "inventory_match_id": None}
            ]
        },
    )
    assert ingest_response.status_code == status.HTTP_200_OK
    payload = ingest_response.json()
    assert not payload["ingested"]
    assert payload["suggestions"]

    suggestions_response = client.get("/inventory/suggestions")
    assert suggestions_response.status_code == status.HTTP_200_OK
    suggestions = suggestions_response.json()
    assert any(s["name"] == "Test Apples" for s in suggestions)

    suggestion_id = suggestions[0]["id"]
    approve_response = client.post(
        f"/inventory/suggestions/{suggestion_id}/approve",
        json={},
    )
    assert approve_response.status_code == status.HTTP_200_OK

    inventory_items = client.get("/inventory").json()
    assert any(item["name"] == "Test Apples" for item in inventory_items)

    suggestions_after = client.get("/inventory/suggestions").json()
    assert all(s["id"] != suggestion_id for s in suggestions_after)
