"""Data access helpers for meal history."""

from __future__ import annotations

from datetime import date
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from remy.models.context import RecentMeal

from .models import MealORM
from .repository import get_session, session_scope


def _to_model(row: MealORM) -> RecentMeal:
    return RecentMeal.model_validate(
        {
            "date": row.date,
            "title": row.title,
            "rating": row.rating,
        }
    )


def list_recent_meals(limit: int = 20) -> List[RecentMeal]:
    """Return the most recent meals ordered by date desc."""

    with session_scope() as session:
        rows = (
            session.execute(
                select(MealORM).order_by(MealORM.date.desc(), MealORM.id.desc()).limit(limit)
            )
            .scalars()
            .all()
        )
        return [_to_model(row) for row in rows]


def record_meal(meal: RecentMeal) -> RecentMeal:
    """Insert or update a meal record (upsert on date + title)."""

    with session_scope() as session:
        db_meal = _upsert_meal(session, meal)
        session.flush()
        return _to_model(db_meal)


def _upsert_meal(session: Session, meal: RecentMeal) -> MealORM:
    existing = (
        session.execute(
            select(MealORM).where(MealORM.date == meal.date, MealORM.title == meal.title)
        ).scalar_one_or_none()
    )
    if existing:
        existing.rating = meal.rating
        return existing

    new_meal = MealORM(date=meal.date, title=meal.title, rating=meal.rating)
    session.add(new_meal)
    return new_meal


def delete_meal(meal_date: date, title: str) -> None:
    """Remove a meal entry, if present."""

    with session_scope() as session:
        row = (
            session.execute(
                select(MealORM).where(MealORM.date == meal_date, MealORM.title == title)
            ).scalar_one_or_none()
        )
        if row:
            session.delete(row)


def raw_session() -> Session:
    """Expose an unmanaged session (primarily for tests)."""

    return get_session()
