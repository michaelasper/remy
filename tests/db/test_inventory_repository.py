from __future__ import annotations

import pytest

from remy.config import get_settings
from remy.db.inventory import (
    create_inventory_item,
    list_inventory,
    update_inventory_item,
)
from remy.db.models import InventoryItemORM
from remy.db.repository import reset_repository_state, session_scope


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "remy.db"
    monkeypatch.setenv("REMY_DATABASE_PATH", str(db_path))
    get_settings.cache_clear()
    reset_repository_state()
    yield
    reset_repository_state()
    monkeypatch.delenv("REMY_DATABASE_PATH", raising=False)
    get_settings.cache_clear()


def test_list_inventory_seeds_defaults(isolated_db):
    items = list_inventory()

    assert len(items) >= 1
    assert items[0].name

    # Ensure running a second time does not duplicate inventory
    items_again = list_inventory()
    assert len(items_again) == len(items)


def test_save_inventory_item_persists_changes(isolated_db):
    base_items = list_inventory()
    original_count = len(base_items)

    saved = create_inventory_item(name="sweet potatoes", quantity=500, unit="g")

    assert saved.id is not None
    assert saved.name == "sweet potatoes"

    items = list_inventory()
    assert len(items) == original_count + 1
    assert any(item.name == "sweet potatoes" for item in items)

    # Update existing item quantity
    updated = update_inventory_item(saved.id, quantity=250)
    assert updated.quantity == 250

    with session_scope() as session:
        db_row = session.get(InventoryItemORM, updated.id)
        assert db_row is not None
        assert db_row.quantity == 250
