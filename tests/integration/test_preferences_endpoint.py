"""Integration tests for preferences endpoints."""

from __future__ import annotations

from fastapi import status


def test_preferences_round_trip(client):
    response = client.get("/preferences")
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert "diet" in payload

    update_payload = {
        "diet": "vegetarian",
        "max_time_min": 40,
        "allergens": ["peanut", "sesame"],
    }
    response = client.put("/preferences", json=update_payload)
    assert response.status_code == status.HTTP_200_OK
    updated = response.json()
    assert updated["diet"] == "vegetarian"
    assert updated["max_time_min"] == 40
    assert updated["allergens"] == ["peanut", "sesame"]

    # Ensure persisted
    response = client.get("/preferences")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["diet"] == "vegetarian"


def test_preferences_accepts_string_allergens(client):
    payload = {
        "diet": "keto",
        "max_time_min": 60,
        "allergens": "peanut, sesame",
    }
    response = client.put("/preferences", json=payload)
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["allergens"] == ["peanut", "sesame"]
