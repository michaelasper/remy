"""Prometheus metrics definitions for Remy."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "remy_http_requests_total",
    "Total number of HTTP requests processed by the Remy API",
    ["method", "path", "status"],
)

REQUEST_LATENCY = Histogram(
    "remy_http_request_duration_seconds",
    "Latency of HTTP requests processed by the Remy API",
    ["method", "path"],
)

OCR_JOBS = Counter(
    "remy_ocr_jobs_total",
    "Number of OCR jobs executed by status",
    ["status"],
)

INGEST_ITEMS = Counter(
    "remy_inventory_items_ingested_total",
    "Number of inventory items ingested from receipts",
    ["result"],
)

__all__ = [
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "OCR_JOBS",
    "INGEST_ITEMS",
]
