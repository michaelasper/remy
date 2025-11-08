"""Integration tests for meal history endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import status

from tests.integration.utils import auth_headers


def test_meals_crud_flow(client):
    response = client.get("/meals")
    assert response.status_code == status.HTTP_200_OK
    initial_count = len(response.json())

    payload = {
        "date": date.today().isoformat(),
        "title": "Test Curry",
        "rating": 4,
        "notes": "Nice and spicy",
    }
    create_response = client.post("/meals", json=payload, headers=auth_headers())
    assert create_response.status_code == status.HTTP_201_CREATED
    created = create_response.json()
    assert created["title"] == "Test Curry"
    assert created["rating"] == 4
    assert created["notes"] == "Nice and spicy"

    updated_response = client.post(
        "/meals",
        json={
            "date": payload["date"],
            "title": payload["title"],
            "rating": 5,
            "notes": "Even better the next day",
        },
        headers=auth_headers(),
    )
    assert updated_response.status_code == status.HTTP_201_CREATED
    assert updated_response.json()["rating"] == 5

    list_response = client.get("/meals")
    assert list_response.status_code == status.HTTP_200_OK
    meals = list_response.json()
    assert len(meals) == initial_count + 1
    assert any(meal["title"] == "Test Curry" for meal in meals)

    delete_response = client.delete(
        f"/meals?date={payload['date']}&title={payload['title']}",
        headers=auth_headers(),
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    final_response = client.get("/meals")
    assert all(meal["title"] != "Test Curry" for meal in final_response.json())
