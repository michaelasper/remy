from __future__ import annotations

import pytest

from remy.config import get_settings
from remy.db.preferences import load_preferences, save_preferences
from remy.db.repository import reset_repository_state
from remy.models.context import Preferences


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


def test_preferences_round_trip(isolated_db):
    defaults = load_preferences()
    assert defaults.diet is None
    assert defaults.allergens == []

    prefs = Preferences(diet="vegan", max_time_min=30, allergens=["peanut"])
    saved = save_preferences(prefs)
    assert saved.diet == "vegan"

    loaded = load_preferences()
    assert loaded.diet == "vegan"
    assert loaded.max_time_min == 30
    assert loaded.allergens == ["peanut"]
