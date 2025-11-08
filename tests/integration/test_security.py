"""Security-related integration tests."""

from __future__ import annotations

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from remy.config import get_settings
from remy.db.repository import reset_repository_state
from remy.server.app import create_app


@pytest.fixture()
def secure_client(tmp_path, monkeypatch) -> TestClient:
    db_path = tmp_path / "secure.db"
    monkeypatch.setenv("REMY_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("REMY_API_TOKEN", "secret-token")
    get_settings.cache_clear()
    reset_repository_state()
    app = create_app()
    client = TestClient(app)
    yield client
    monkeypatch.delenv("REMY_API_TOKEN", raising=False)
    reset_repository_state()
    get_settings.cache_clear()


def test_requests_require_api_token(secure_client):
    response = secure_client.post(
        "/inventory",
        json={"name": "lentils", "quantity": 2, "unit": "bag"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    headers = {"Authorization": "Bearer secret-token"}
    response = secure_client.post(
        "/inventory",
        json={"name": "lentils", "quantity": 2, "unit": "bag"},
        headers=headers,
    )
    assert response.status_code == status.HTTP_201_CREATED


def test_shopping_list_requires_api_token(secure_client):
    response = secure_client.post(
        "/shopping-list",
        json={"name": "eggs", "quantity": 12, "unit": "count"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    headers = {"Authorization": "Bearer secret-token"}
    response = secure_client.post(
        "/shopping-list",
        json={"name": "eggs", "quantity": 12, "unit": "count"},
        headers=headers,
    )
    assert response.status_code == status.HTTP_201_CREATED


def test_plan_endpoint_enforces_api_token(secure_client):
    payload = {
        "date": "2025-01-01",
        "prefs": {"diet": None, "max_time_min": 30, "allergens": []},
        "recent_meals": [],
        "inventory": [],
        "leftovers": [],
        "constraints": {"attendees": 2, "time_window": "evening"},
    }

    response = secure_client.post("/plan", json=payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    headers = {"Authorization": "Bearer secret-token"}
    response = secure_client.post("/plan", json=payload, headers=headers)
    assert response.status_code == status.HTTP_200_OK
