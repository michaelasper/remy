"""Integration tests for the inventory endpoints."""

from __future__ import annotations

from fastapi import status


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
    assert "Inventory Overview" in response.text
    assert "GET <code>/inventory</code>" in response.text
