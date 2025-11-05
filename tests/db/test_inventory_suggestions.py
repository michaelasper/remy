"""Tests for inventory suggestion persistence helpers."""

from __future__ import annotations

import pytest

from remy.config import get_settings
from remy.db.inventory import list_inventory
from remy.db.inventory_suggestions import (
    approve_suggestion,
    create_suggestion,
    delete_suggestion,
    list_suggestions,
)
from remy.db.repository import reset_repository_state


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "suggestions.db"
    monkeypatch.setenv("REMY_DATABASE_PATH", str(db_path))
    get_settings.cache_clear()
    reset_repository_state()
    yield
    reset_repository_state()
    monkeypatch.delenv("REMY_DATABASE_PATH", raising=False)
    get_settings.cache_clear()


def test_create_list_and_delete_suggestion(isolated_db):
    suggestion = create_suggestion(
        receipt_id=1,
        name="Test Item",
        quantity=1.5,
        unit="kg",
        confidence=0.65,
        notes="Check freshness",
    )
    assert suggestion.receipt_id == 1
    suggestions = list_suggestions()
    assert len(suggestions) == 1
    assert suggestions[0].name == "Test Item"

    delete_suggestion(suggestion.id)
    assert list_suggestions() == []


def test_approve_suggestion_creates_inventory(isolated_db):
    suggestion = create_suggestion(
        receipt_id=2,
        name="Blueberries",
        quantity=3,
        unit="pints",
        confidence=0.7,
    )

    approved = approve_suggestion(suggestion.id)
    assert approved.inventory_match_id is not None
    inventory = list_inventory()
    assert any(item.name == "Blueberries" for item in inventory)

    with pytest.raises(ValueError):
        delete_suggestion(suggestion.id)
