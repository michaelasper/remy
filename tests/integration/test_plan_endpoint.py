"""Integration tests for the FastAPI plan endpoint."""

from __future__ import annotations

from unittest.mock import Mock

from fastapi import status

from remy.config import get_settings
from remy.server import deps


def _auth_headers():
    token = get_settings().api_token
    return {"Authorization": f"Bearer {token}"} if token else {}


def test_plan_endpoint_returns_plan(client, app, sample_context_payload, sample_plan):
    """The /plan endpoint should return the plan produced by the generator dependency."""

    mock_generator = Mock(return_value=sample_plan)
    app.dependency_overrides[deps.get_plan_generator] = lambda: mock_generator

    response = client.post("/plan", json=sample_context_payload, headers=_auth_headers())

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["date"] == sample_plan.date.isoformat()
    assert response.json()["candidates"][0]["title"] == sample_plan.candidates[0].title
    mock_generator.assert_called_once()

    shopping_list = client.get("/shopping-list").json()
    names = {item["name"] for item in shopping_list}
    assert "green onions" in names, "expected shopping shortfall to sync into shopping list"


def test_plan_endpoint_validates_payload(client):
    """Invalid payloads should be rejected by FastAPI validation."""

    response = client.post("/plan", json={"date": "not-a-date"}, headers=_auth_headers())

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
