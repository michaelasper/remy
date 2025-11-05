"""Tests for the heuristic receipt parser."""

from __future__ import annotations

from datetime import date

from remy.models.context import InventoryItem
from remy.ocr.parser import ReceiptParser


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

