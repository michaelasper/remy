"""Integration tests for the interactive web UI."""

from __future__ import annotations

from fastapi import status


def test_ui_homepage_served(client):
    """GET / should return the HTML UI page."""

    response = client.get("/")

    assert response.status_code == status.HTTP_200_OK
    assert "Remy Dinner Planner" in response.text
    assert "<textarea" in response.text
