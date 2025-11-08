"""Leftover data access helpers."""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import select

from remy.models.context import LeftoverItem

from .models import LeftoverORM
from .repository import session_scope

_UNSET = object()


def _to_model(row: LeftoverORM) -> LeftoverItem:
    payload: dict[str, object] = {
        "id": row.id,
        "name": row.name,
        "qty": row.quantity,
        "unit": row.unit,
        "best_before": row.best_before,
    }
    if row.notes:
        payload["notes"] = row.notes
    return LeftoverItem.model_validate(payload)


def list_leftovers() -> List[LeftoverItem]:
    """Return all recorded leftovers sorted by urgency."""

    with session_scope() as session:
        rows = (
            session.execute(
                select(LeftoverORM).order_by(
                    LeftoverORM.best_before.is_(None),
                    LeftoverORM.best_before,
                    LeftoverORM.name,
                )
            )
            .scalars()
            .all()
        )
        return [_to_model(row) for row in rows]


def create_leftover_item(
    *,
    name: str,
    quantity: float,
    unit: str,
    best_before: Optional[date] = None,
    notes: Optional[str] = None,
) -> LeftoverItem:
    with session_scope() as session:
        db_item = LeftoverORM(
            name=name,
            quantity=float(quantity),
            unit=unit,
            best_before=best_before,
            notes=notes,
        )
        session.add(db_item)
        session.flush()
        return _to_model(db_item)


def update_leftover_item(
    leftover_id: int,
    *,
    name: Optional[str] = None,
    quantity: Optional[float] = None,
    unit: Optional[str] = None,
    best_before: Optional[date] | object = _UNSET,
    notes: Optional[str] | object = _UNSET,
) -> LeftoverItem:
    with session_scope() as session:
        db_item = session.get(LeftoverORM, leftover_id)
        if db_item is None:
            raise ValueError(f"Leftover item {leftover_id} not found")

        if name is not None:
            db_item.name = name
        if quantity is not None:
            db_item.quantity = float(quantity)
        if unit is not None:
            db_item.unit = unit
        if best_before is not _UNSET:
            db_item.best_before = best_before  # type: ignore[assignment]
        if notes is not _UNSET:
            db_item.notes = notes  # type: ignore[assignment]

        session.flush()
        return _to_model(db_item)


def delete_leftover_item(leftover_id: int) -> None:
    with session_scope() as session:
        db_item = session.get(LeftoverORM, leftover_id)
        if db_item is None:
            raise ValueError(f"Leftover item {leftover_id} not found")
        session.delete(db_item)


def get_leftover_item(leftover_id: int) -> Optional[LeftoverItem]:
    with session_scope() as session:
        row = session.get(LeftoverORM, leftover_id)
        if row is None:
            return None
        return _to_model(row)
