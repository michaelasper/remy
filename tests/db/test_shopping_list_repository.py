"""Unit tests for the shopping list repository helpers."""

from __future__ import annotations

import pytest

from remy.db.shopping_list import (
    create_shopping_item,
    delete_shopping_item,
    get_shopping_item,
    list_shopping_items,
    reset_shopping_list,
    update_shopping_item,
)


def test_create_and_list_shopping_items():
    create_shopping_item(name="milk", quantity=2, unit="cartons")
    create_shopping_item(name="spinach", quantity=1, unit="bag")

    items = list_shopping_items()
    assert [item.name for item in items] == ["milk", "spinach"]
    assert all(item.id for item in items)


def test_update_and_delete_shopping_item():
    item = create_shopping_item(name="olive oil", quantity=1, unit="bottle")

    updated = update_shopping_item(
        item.id,
        quantity=2,
        notes="cold pressed only",
        is_checked=True,
    )
    assert updated.is_checked is True
    assert updated.quantity == 2
    assert updated.notes == "cold pressed only"

    toggled = update_shopping_item(item.id, is_checked=False)
    assert toggled.is_checked is False

    delete_shopping_item(item.id)
    assert get_shopping_item(item.id) is None


def test_reset_shopping_list():
    create_shopping_item(name="lemons", quantity=4, unit="pc")
    create_shopping_item(name="garlic", quantity=1, unit="head")

    reset_shopping_list()

    assert list_shopping_items() == []


def test_update_missing_item_raises():
    with pytest.raises(ValueError):
        update_shopping_item(999, name="nope")
