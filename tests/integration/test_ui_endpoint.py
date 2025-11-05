"""Integration tests for the interactive web UI."""

from __future__ import annotations

from fastapi import status


def test_ui_homepage_served(client):
    """GET / should return the HTML UI page."""

    response = client.get("/")

    assert response.status_code == status.HTTP_200_OK
    assert "Remy Control Center" in response.text
    assert "Vue.createApp" in response.text


def test_receipts_page_served(client):
    response = client.get("/receipts/view")

    assert response.status_code == status.HTTP_200_OK
    assert "Remy Control Center" in response.text
    assert "Upload Receipt" in response.text
