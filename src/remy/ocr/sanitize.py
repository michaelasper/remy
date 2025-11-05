"""Utilities for sanitizing OCR output."""

from __future__ import annotations

import re
from typing import Iterable

_CARD_PATTERN = re.compile(r"(?<!\d)(\d[\s-]?){12,19}(?!\d)")


def sanitize_text(value: str) -> str:
    """Mask sensitive numeric sequences that resemble payment identifiers."""

    def _mask(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group())
        if len(digits) < 12:
            return match.group()
        masked = digits[:4] + "*" * (len(digits) - 8) + digits[-4:]
        return masked

    return _CARD_PATTERN.sub(_mask, value)


def sanitize_words(words: Iterable[str]) -> list[str]:
    """Apply masking to a collection of word tokens."""

    return [sanitize_text(word) for word in words]


__all__ = ["sanitize_text", "sanitize_words"]
