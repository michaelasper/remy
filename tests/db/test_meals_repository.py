from __future__ import annotations

from datetime import date

import pytest

from remy.config import get_settings
from remy.db.meals import delete_meal, list_recent_meals, record_meal
from remy.db.repository import reset_repository_state
from remy.models.context import RecentMeal


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


def test_record_and_list_meals(isolated_db):
    meal = RecentMeal(date=date(2025, 1, 1), title="Tofu Stir Fry", rating=4)
    record_meal(meal)

    meals = list_recent_meals()
    assert meals
    assert meals[0].title == "Tofu Stir Fry"

    # Update rating
    updated = record_meal(RecentMeal(date=meal.date, title=meal.title, rating=5))
    assert updated.rating == 5

    meals_after = list_recent_meals()
    assert meals_after[0].rating == 5


def test_delete_meal(isolated_db):
    meal = RecentMeal(date=date(2025, 1, 2), title="Chili", rating=None)
    record_meal(meal)
    assert list_recent_meals()

    delete_meal(meal.date, meal.title)
    assert not list_recent_meals()
