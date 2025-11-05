"""Heuristic receipt text parser and inventory matcher."""

from __future__ import annotations

import dataclasses
import logging
import re
from datetime import date
from typing import Callable, Iterable, List, Optional

from rapidfuzz import fuzz, process

from remy.db.inventory import list_inventory
from remy.models.context import InventoryItem
from remy.models.receipt import ReceiptLineItem, ReceiptStructuredData

logger = logging.getLogger(__name__)

_STOP_WORDS = {"subtotal", "sub total", "tax", "total", "balance", "tender", "change"}
_UNIT_TOKENS = {
    "lb",
    "lbs",
    "kg",
    "g",
    "oz",
    "ea",
    "each",
    "ct",
    "pk",
    "pc",
    "pcs",
    "l",
    "ml",
    "pack",
    "doz",
}
_CURRENCY_SIGNS = {"$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY", "₹": "INR"}


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


@dataclasses.dataclass
class InventoryMatch:
    item_id: int
    name: str
    score: float


class ReceiptParser:
    """Parse OCR'd receipt text into structured line items."""

    def __init__(
        self,
        *,
        inventory_provider: Callable[[], Iterable[InventoryItem]] = list_inventory,
        fuzzy_threshold: float = 70.0,
    ) -> None:
        self._inventory_provider = inventory_provider
        self._fuzzy_threshold = fuzzy_threshold
        self._inventory_cache: Optional[List[InventoryItem]] = None

    def parse(self, text: str) -> ReceiptStructuredData:
        lines = [_normalize_line(line) for line in text.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            return ReceiptStructuredData(items=[])

        store_name = self._infer_store_name(lines)
        purchase_date = self._extract_date(text)
        currency = self._detect_currency(text)

        items: List[ReceiptLineItem] = []
        subtotal = tax = total = None

        for line in lines:
            lower = line.lower()
            if any(stop in lower for stop in _STOP_WORDS):
                amount = self._extract_amount_from_text(line)
                if "tax" in lower:
                    tax = amount or tax
                elif "subtotal" in lower:
                    subtotal = amount or subtotal
                else:
                    total = amount or total
                continue

            parsed = self._parse_line(line)
            if parsed is None:
                continue

            match = self._match_inventory(parsed.name)
            if match:
                parsed.inventory_match_id = match.item_id
                parsed.inventory_match_name = match.name
                parsed.inventory_match_score = match.score
                parsed.confidence = max(parsed.confidence, min(1.0, match.score / 100))

            items.append(parsed)

        return ReceiptStructuredData(
            store_name=store_name,
            purchase_date=purchase_date,
            currency=currency,
            items=items,
            subtotal=subtotal,
            tax=tax,
            total=total,
        )

    def _infer_store_name(self, lines: List[str]) -> Optional[str]:
        if not lines:
            return None
        for line in lines[:3]:
            alpha = sum(ch.isalpha() for ch in line)
            if alpha >= 3 and (alpha / max(1, len(line.replace(" ", "")))) > 0.5:
                return line.title()
        return lines[0].title()

    def _extract_date(self, text: str) -> Optional[date]:
        patterns = [
            r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})",
            r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            try:
                parts = [int(value) for value in match.groups()]
                if len(parts[0].__str__()) == 4:
                    year, month, day = parts
                else:
                    month, day, year = parts
                    if year < 100:
                        year += 2000
                return date(year, month, day)
            except ValueError:
                continue
        return None

    def _detect_currency(self, text: str) -> Optional[str]:
        for sign, code in _CURRENCY_SIGNS.items():
            if sign in text:
                return code
        return None

    def _parse_line(self, line: str) -> Optional[ReceiptLineItem]:
        amount_match = re.search(r"(\d+\.\d{2})\s*$", line)
        if not amount_match:
            return None
        try:
            price = float(amount_match.group(1))
        except ValueError:
            return None

        head = line[: amount_match.start()].strip()
        name, quantity, unit = self._extract_quantity_and_name(head)

        confidence = 0.6 if name else 0.3
        if quantity is not None:
            confidence += 0.2

        unit_price = None
        if quantity and quantity > 0:
            unit_price = round(price / quantity, 2)

        return ReceiptLineItem(
            raw_text=line,
            name=name or head,
            quantity=quantity,
            unit=unit,
            unit_price=unit_price,
            total_price=price,
            confidence=min(confidence, 1.0),
        )

    def _extract_quantity_and_name(self, prefix: str) -> tuple[str, Optional[float], Optional[str]]:
        tokens = prefix.split()
        if not tokens:
            return prefix, None, None

        quantity = None
        unit = None

        if tokens[0].replace("x", "").replace("X", "").replace(".", "", 1).isdigit():
            qty_token = tokens.pop(0)
            qty_token = qty_token.replace("x", "").replace("X", "")
            try:
                quantity = float(qty_token)
            except ValueError:
                quantity = None

        if tokens:
            last = tokens[-1].lower()
            if last in _UNIT_TOKENS:
                unit = tokens.pop(-1)

        if quantity is None and tokens:
            last = tokens[-1]
            if re.fullmatch(r"\d+(?:\.\d+)?", last):
                try:
                    quantity = float(last)
                    tokens.pop(-1)
                except ValueError:
                    quantity = None

        name = " ".join(tokens).strip()
        return name, quantity, unit

    @staticmethod
    def _extract_amount_from_text(text: str) -> Optional[float]:
        match = re.search(r"(\d+\.\d{2})\s*$", text)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    def _match_inventory(self, name: str) -> Optional[InventoryMatch]:
        inventory = self._get_inventory()
        if not inventory:
            return None

        choices = [item.name for item in inventory]
        result = process.extractOne(
            name, choices, scorer=fuzz.WRatio, score_cutoff=self._fuzzy_threshold
        )
        if not result:
            return None

        matched_name, score, index = result
        matched_item = inventory[index]
        return InventoryMatch(item_id=matched_item.id, name=matched_name, score=score)

    def _get_inventory(self) -> List[InventoryItem]:
        if self._inventory_cache is None:
            try:
                self._inventory_cache = list(self._inventory_provider())
            except Exception:  # pragma: no cover - inventory lookup is best effort
                logger.exception("Unable to load inventory; skipping fuzzy matches")
                self._inventory_cache = []
        return self._inventory_cache


__all__ = ["ReceiptParser"]
