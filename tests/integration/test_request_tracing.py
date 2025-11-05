"""Integration tests covering request ID propagation and middleware."""

from __future__ import annotations


def test_request_id_echoed_when_provided(client):
    request_id = "test-request-123"
    response = client.get("/inventory", headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id


def test_request_id_generated_when_missing(client):
    response = client.get("/inventory")
    assert response.status_code == 200
    generated = response.headers.get("X-Request-ID")
    assert generated
    assert len(generated) >= 8
