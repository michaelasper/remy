"""Integration tests for the shopping list endpoints."""

from __future__ import annotations

import pytest
from fastapi import status

from remy.config import get_settings


def _auth_headers():
    token = get_settings().api_token
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def test_shopping_list_crud_and_add_to_inventory(client):
    response = client.get("/shopping-list")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []

    headers = _auth_headers()
    create_payload = {"name": "milk", "quantity": 2, "unit": "carton", "notes": "oat milk"}
    response = client.post("/shopping-list", json=create_payload, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED
    item = response.json()
    item_id = item["id"]
    assert item["name"] == "milk"

    response = client.put(f"/shopping-list/{item_id}", json={"is_checked": True}, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["is_checked"] is True

    response = client.post(
        f"/shopping-list/{item_id}/add-to-inventory", json={}, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED
    inventory_item = response.json()
    assert inventory_item["name"] == "milk"
    assert inventory_item["qty"] == pytest.approx(2.0)

    response = client.get("/shopping-list")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


def test_shopping_list_reset(client):
    headers = _auth_headers()
    client.post("/shopping-list", json={"name": "lemons", "quantity": 3, "unit": "pc"}, headers=headers)
    client.post("/shopping-list", json={"name": "garlic", "quantity": 1, "unit": "head"}, headers=headers)

    response = client.post("/shopping-list/reset", headers=headers)
    assert response.status_code == status.HTTP_204_NO_CONTENT

    response = client.get("/shopping-list")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []
