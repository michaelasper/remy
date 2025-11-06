"""Integration tests for metrics endpoint."""

from __future__ import annotations


def test_metrics_endpoint_available(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.content.decode()
    assert "remy_http_requests_total" in body
