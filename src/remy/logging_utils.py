"""Logging configuration helpers with secret redaction support."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Iterable, List, Sequence

REDACTED = "[redacted]"

_BEARER_PATTERN = re.compile(r"(Bearer\s+)([A-Za-z0-9\-._~+/=]+)", re.IGNORECASE)
_API_TOKEN_PATTERN = re.compile(r"(api_token=)([^&\s]+)", re.IGNORECASE)
_X_API_KEY_PATTERN = re.compile(r"(X-API-Key=)([^&\s]+)", re.IGNORECASE)


def _mask_known_patterns(value: str) -> str:
    """Mask standard auth token patterns."""

    value = _BEARER_PATTERN.sub(r"\1" + REDACTED, value)
    value = _API_TOKEN_PATTERN.sub(r"\1" + REDACTED, value)
    value = _X_API_KEY_PATTERN.sub(r"\1" + REDACTED, value)
    return value


def _normalize_secret(secret: str) -> str:
    return secret.strip()


def _sanitize(message: str, secrets: Sequence[str]) -> str:
    sanitized = _mask_known_patterns(message)
    for secret in secrets:
        if not secret:
            continue
        sanitized = sanitized.replace(secret, REDACTED)
    return sanitized


class SensitiveDataFilter(logging.Filter):
    """Filter that redacts configured secrets from log records."""

    def __init__(self, secrets: Iterable[str]):
        super().__init__()
        self._secrets: List[str] = [
            _normalize_secret(secret) for secret in secrets if _normalize_secret(secret)
        ]

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401 - standard interface
        if not self._secrets:
            return True

        message = record.getMessage()
        sanitized = _sanitize(message, self._secrets)
        if sanitized != message:
            record.msg = sanitized
            record.args = ()

        # Sanitize extra dict-like payloads commonly used by logging frameworks.
        for key, value in list(vars(record).items()):
            if isinstance(value, str):
                setattr(record, key, _sanitize(value, self._secrets))

        return True


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - override
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if request_id := getattr(record, "request_id", None):
            payload["request_id"] = request_id

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        if record.stack_info:
            payload["stack"] = record.stack_info

        return json.dumps(payload, ensure_ascii=True)


def configure_logging(level_name: str, fmt: str, secrets: Iterable[str]) -> None:
    """Configure root logging with optional JSON output and secret redaction."""

    numeric_level = getattr(logging, level_name.upper(), logging.INFO)
    format_normalized = (fmt or "plain").lower()

    handler = logging.StreamHandler()
    if format_normalized == "json":
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    handler.setFormatter(formatter)

    filter_ = SensitiveDataFilter(secrets)
    handler.addFilter(filter_)

    root = logging.getLogger()
    root.handlers = []
    root.addHandler(handler)
    root.setLevel(numeric_level)

    logging.captureWarnings(True)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.setLevel(numeric_level)
        logger.propagate = True
        logger.addFilter(filter_)
