"""Heuristic receipt text parser and inventory matcher."""
# mypy: ignore-errors

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
from remy.ocr.llm_client import ReceiptLLMClient

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

_KNOWN_PRODUCTS: dict[str, list[str]] = {
    "Bananas": [r"\bbanana(?:s)?\b"],
    "Red apples": [r"\bred (?:apple|apples)\b", r"\bred delicious"],
    "Green apples": [r"\bgreen (?:apple|apples)\b"],
    "Roma tomatoes": [r"\broma (?:tomato|tomatoes)\b"],
    "Iceberg lettuce": [r"\biceberg (?:lettuce)?\b"],
    "Avocados": [r"\bavocado(?:s)?\b"],
    "Cucumber": [r"\bcucumber(?:s)?\b"],
    "Blueberries": [r"\bblueberr(?:y|ies)\b"],
    "Broccoli": [r"\bbroccol[iy]\b"],
    "Mushrooms": [r"\bmushroom(?:s)?\b"],
    "Ginger": [r"\bginger\b"],
}


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _canonical_name(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value).strip().lower()
    no_punct = re.sub(r"[^\w\s]", " ", collapsed)
    return re.sub(r"\s+", " ", no_punct).strip()


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
        llm_client: ReceiptLLMClient | None = None,
    ) -> None:
        self._inventory_provider = inventory_provider
        self._fuzzy_threshold = fuzzy_threshold
        self._inventory_cache: Optional[List[InventoryItem]] = None
        self._llm_client = llm_client

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

        heuristic_augments = self._augment_known_products(text, items)
        items, llm_summary = self._apply_llm_enhancements(text, items)

        if heuristic_augments:
            logger.info(
                "Receipt heuristics added %s item(s): %s",
                len(heuristic_augments),
                heuristic_augments,
            )
        if llm_summary.get("enabled"):
            logger.info(
                "Receipt LLM enhancement summary added=%s enriched=%s",
                len(llm_summary.get("added", [])),
                len(llm_summary.get("enriched", [])),
            )

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

    def _augment_known_products(self, text: str, items: List[ReceiptLineItem]) -> List[str]:
        existing = {_normalize_line(item.name).strip().lower() for item in items}
        lowered = text.lower()
        additions: List[str] = []
        for canonical, patterns in _KNOWN_PRODUCTS.items():
            normalized = canonical.strip().lower()
            if normalized in existing:
                continue
            if any(re.search(pattern, lowered) for pattern in patterns):
                items.append(
                    ReceiptLineItem(
                        raw_text=canonical,
                        name=canonical,
                        quantity=None,
                        unit=None,
                        unit_price=None,
                        total_price=None,
                        confidence=0.85,
                    )
                )
                existing.add(normalized)
                additions.append(canonical)
        return additions

    def _apply_llm_enhancements(
        self,
        text: str,
        items: List[ReceiptLineItem],
    ) -> tuple[List[ReceiptLineItem], dict[str, object]]:
        summary: dict[str, object] = {
            "enabled": bool(self._llm_client),
            "added": [],
            "enriched": [],
        }
        if not self._llm_client:
            return items, summary
        try:
            llm_items = self._llm_client.parse_items(text, items)
        except Exception as exc:
            logger.warning("Receipt LLM enhancement failed: %s", exc)
            summary["error"] = str(exc)
            return items, summary
        if not llm_items:
            return items, summary
        merged_items, merge_summary = self._merge_llm_items(items, llm_items)
        summary.update(merge_summary)
        return merged_items, summary

    def _merge_llm_items(
        self,
        base_items: List[ReceiptLineItem],
        llm_items: List[ReceiptLineItem],
    ) -> tuple[List[ReceiptLineItem], dict[str, List[str]]]:
        normalized = {_canonical_name(item.name): item for item in base_items}
        added: List[str] = []
        enriched: List[str] = []
        for candidate in llm_items:
            key = _canonical_name(candidate.name)
            existing = normalized.get(key)
            if existing:
                updated_fields: List[str] = []
                if existing.quantity is None and candidate.quantity is not None:
                    existing.quantity = candidate.quantity
                    updated_fields.append("quantity")
                if not existing.unit and candidate.unit:
                    existing.unit = candidate.unit
                    updated_fields.append("unit")
                if existing.total_price is None and candidate.total_price is not None:
                    existing.total_price = candidate.total_price
                    updated_fields.append("total_price")
                if existing.unit_price is None and candidate.unit_price is not None:
                    existing.unit_price = candidate.unit_price
                    updated_fields.append("unit_price")
                existing.confidence = max(existing.confidence, candidate.confidence)
                if updated_fields:
                    enriched.append(f"{existing.name} (+{', '.join(updated_fields)})")
                continue

            match = self._match_inventory(candidate.name)
            if match:
                candidate.inventory_match_id = match.item_id
                candidate.inventory_match_name = match.name
                candidate.inventory_match_score = match.score
                candidate.confidence = max(candidate.confidence, min(1.0, match.score / 100))
            base_items.append(candidate)
            normalized[key] = candidate
            added.append(candidate.name)
        return base_items, {"added": added, "enriched": enriched}

    def _get_inventory(self) -> List[InventoryItem]:
        if self._inventory_cache is None:
            try:
                self._inventory_cache = list(self._inventory_provider())
            except Exception:  # pragma: no cover - inventory lookup is best effort
                logger.exception("Unable to load inventory; skipping fuzzy matches")
                self._inventory_cache = []
        return self._inventory_cache


__all__ = ["ReceiptParser"]
