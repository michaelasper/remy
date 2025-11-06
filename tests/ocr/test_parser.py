"""Tests for the heuristic receipt parser."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from remy.models.context import InventoryItem
from remy.ocr.parser import ReceiptParser

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "receipts"


def test_parser_extracts_store_date_and_items():
    sample_text = """
FRESH MART
123 FOOD AVENUE
02/10/2025 18:45
Milk Whole 1L 3.99
Bananas 2 1.50
Eggs 12 ct 2.99
Subtotal 8.48
Tax 0.60
Total 9.08
""".strip()

    inventory = [
        InventoryItem(id=1, name="milk whole 1l", qty=1000, unit="ml"),
        InventoryItem(id=2, name="banana", qty=6, unit="count"),
    ]

    parser = ReceiptParser(inventory_provider=lambda: inventory, fuzzy_threshold=60)
    result = parser.parse(sample_text)

    assert result.store_name == "Fresh Mart"
    assert result.purchase_date == date(2025, 2, 10)
    assert result.total == 9.08
    assert result.subtotal == 8.48
    assert result.tax == 0.60
    assert len(result.items) == 3

    milk = result.items[0]
    assert milk.inventory_match_id == 1
    assert milk.quantity is None
    assert milk.total_price == 3.99

    bananas = result.items[1]
    assert bananas.name.lower().startswith("bananas")
    assert bananas.quantity == 2
    assert bananas.inventory_match_id == 2
    assert bananas.inventory_match_score and bananas.inventory_match_score > 60

    eggs = result.items[2]
    assert eggs.unit.lower() == "ct"
    assert eggs.quantity == 12


@pytest.mark.parametrize("epsilon", [0.05])
def test_parser_matches_fixture(epsilon: float) -> None:
    raw_text = (FIXTURES_DIR / "sample_receipt.txt").read_text(encoding="utf-8")
    expected: dict[str, Any] = json.loads(
        (FIXTURES_DIR / "sample_receipt_expected.json").read_text(encoding="utf-8")
    )

    parser = ReceiptParser(fuzzy_threshold=60)
    result = parser.parse(raw_text)

    assert result.store_name == expected["store_name"]
    if expected.get("purchase_date"):
        assert result.purchase_date == date.fromisoformat(expected["purchase_date"])
    if expected.get("total") is not None and result.total is not None:
        assert abs(result.total - expected["total"]) <= epsilon

    assert len(result.items) >= len(expected["items"])
    for expected_item in expected["items"]:
        match = next(
            (
                item
                for item in result.items
                if expected_item["name"].lower() in item.name.lower()
            ),
            None,
        )
        assert match is not None, f"Missing item for {expected_item['name']}"
        if expected_item.get("total_price") is not None and match.total_price is not None:
            assert abs(match.total_price - expected_item["total_price"]) <= epsilon
        if expected_item.get("quantity") is not None and match.quantity is not None:
            assert abs(match.quantity - expected_item["quantity"]) <= epsilon


def test_known_product_heuristics():
    sample_text = """
Bananas $1.20
Red Apples $3.50
Green Apples $2.80
Roma Tomatoes $4.10
Iceberg Lettuce $1.99
Avocados $5.00
Cucumber $0.95
Blueberries $3.99
Broccoli $2.25
Mushrooms $2.15
Ginger $1.05
""".strip()

    parser = ReceiptParser()
    result = parser.parse(sample_text)
    names = {item.name.lower() for item in result.items}
    expected = {
        "bananas",
        "red apples",
        "green apples",
        "roma tomatoes",
        "iceberg lettuce",
        "avocados",
        "cucumber",
        "blueberries",
        "broccoli",
        "mushrooms",
        "ginger",
    }
    assert expected.issubset(names)
