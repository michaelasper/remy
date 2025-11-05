"""Tests for logging utilities and sensitive data redaction."""

from __future__ import annotations

import logging

import pytest

from remy.logging_utils import configure_logging


@pytest.mark.parametrize("fmt", ["plain", "json"])
def test_sensitive_data_filter_redacts_tokens(fmt):
    secret = "top-secret-token"
    configure_logging("INFO", fmt, [secret])

    handler = logging.getLogger().handlers[0]
    record = logging.LogRecord(
        name="remy.test.redaction",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="Authorization header Bearer %s",
        args=(secret,),
        exc_info=None,
    )

    for filter_ in handler.filters:
        filter_.filter(record)

    formatted = handler.format(record)
    assert secret not in formatted
    assert "[redacted]" in formatted
