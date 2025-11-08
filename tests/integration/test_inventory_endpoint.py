"""Integration tests for the inventory endpoints."""

from __future__ import annotations

from fastapi import status

from tests.integration.utils import auth_headers


def test_inventory_endpoint_returns_items(client):
    response = client.get("/inventory")

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert isinstance(payload, list)
    assert payload, "Expected default inventory to be non-empty"
    assert {"id", "name", "unit"}.issubset(payload[0].keys())


def test_inventory_view_serves_html(client):
    response = client.get("/inventory/view")

    assert response.status_code == status.HTTP_200_OK
    assert "Remy Control Center" in response.text
    assert "Add Inventory Item" in response.text


def test_inventory_create_update_delete_flow(client):
    create_payload = {
        "name": "canned tomatoes",
        "quantity": 4,
        "unit": "can",
        "best_before": "2026-01-01",
    }
    response = client.post("/inventory", json=create_payload, headers=auth_headers())
    assert response.status_code == status.HTTP_201_CREATED
    created = response.json()
    item_id = created["id"]
    assert created["name"] == "canned tomatoes"

    response = client.put(
        f"/inventory/{item_id}",
        json={"quantity": 3},
        headers=auth_headers(),
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["qty"] == 3

    response = client.delete(f"/inventory/{item_id}", headers=auth_headers())
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Ensure the item no longer exists
    items = client.get("/inventory").json()
    assert all(item["name"] != "canned tomatoes" for item in items)
