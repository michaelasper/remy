"""Integration tests for the leftovers endpoints."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import status

from remy.config import get_settings


def _auth_headers():
    token = get_settings().api_token
    return {"Authorization": f"Bearer {token}"} if token else {}


def test_leftovers_crud_flow(client):
    response = client.get("/leftovers")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []

    headers = _auth_headers()
    create_payload = {
        "name": "lentil soup",
        "quantity": 2,
        "unit": "serving",
        "best_before": (date.today() + timedelta(days=1)).isoformat(),
        "notes": "Finish tomorrow",
    }
    response = client.post("/leftovers", json=create_payload, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED
    created = response.json()
    leftover_id = created["id"]
    assert created["name"] == "lentil soup"
    assert created["qty"] == 2
    assert created["notes"] == "Finish tomorrow"

    response = client.put(
        f"/leftovers/{leftover_id}",
        json={"quantity": 1.5, "notes": "Lunch portion"},
        headers=headers,
    )
    assert response.status_code == status.HTTP_200_OK
    updated = response.json()
    assert updated["qty"] == 1.5
    assert updated["notes"] == "Lunch portion"

    response = client.get("/leftovers")
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["name"] == "lentil soup"

    response = client.delete(f"/leftovers/{leftover_id}", headers=headers)
    assert response.status_code == status.HTTP_204_NO_CONTENT

    response = client.get("/leftovers")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []
