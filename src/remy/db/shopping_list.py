"""Shopping list persistence helpers."""
# mypy: ignore-errors

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import delete, select

from remy.models.shopping import ShoppingListItem

from .models import ShoppingListItemORM
from .repository import session_scope

_UNSET = object()


def _to_model(row: ShoppingListItemORM) -> ShoppingListItem:
    return ShoppingListItem.model_validate(
        {
            "id": row.id,
            "name": row.name,
            "quantity": row.quantity,
            "unit": row.unit,
            "notes": row.notes,
            "is_checked": row.is_checked,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def list_shopping_items() -> List[ShoppingListItem]:
    """Return all shopping list items (unchecked items first)."""

    with session_scope() as session:
        rows = (
            session.execute(
                select(ShoppingListItemORM).order_by(
                    ShoppingListItemORM.is_checked.asc(),
                    ShoppingListItemORM.created_at.asc(),
                )
            )
            .scalars()
            .all()
        )
        return [_to_model(row) for row in rows]


def create_shopping_item(
    *,
    name: str,
    quantity: Optional[float] = None,
    unit: Optional[str] = None,
    notes: Optional[str] = None,
) -> ShoppingListItem:
    with session_scope() as session:
        db_item = ShoppingListItemORM(
            name=name.strip(),
            quantity=float(quantity) if quantity is not None else None,
            unit=unit.strip() if unit else None,
            notes=notes,
            is_checked=False,
        )
        session.add(db_item)
        session.flush()
        return _to_model(db_item)


def update_shopping_item(
    item_id: int,
    *,
    name: str | object = _UNSET,
    quantity: float | None | object = _UNSET,
    unit: str | None | object = _UNSET,
    notes: str | None | object = _UNSET,
    is_checked: bool | object = _UNSET,
) -> ShoppingListItem:
    with session_scope() as session:
        db_item = session.get(ShoppingListItemORM, item_id)
        if db_item is None:
            raise ValueError(f"Shopping list item {item_id} not found")

        if name is not _UNSET:
            db_item.name = str(name).strip()
        if quantity is not _UNSET:
            db_item.quantity = float(quantity) if quantity is not None else None  # type: ignore[arg-type]
        if unit is not _UNSET:
            db_item.unit = unit.strip() if unit else None  # type: ignore[union-attr]
        if notes is not _UNSET:
            db_item.notes = notes  # type: ignore[assignment]
        if is_checked is not _UNSET:
            db_item.is_checked = bool(is_checked)

        session.flush()
        return _to_model(db_item)


def delete_shopping_item(item_id: int) -> None:
    with session_scope() as session:
        db_item = session.get(ShoppingListItemORM, item_id)
        if db_item is None:
            raise ValueError(f"Shopping list item {item_id} not found")
        session.delete(db_item)


def reset_shopping_list() -> None:
    """Remove all shopping list items."""

    with session_scope() as session:
        session.execute(delete(ShoppingListItemORM))


def get_shopping_item(item_id: int) -> Optional[ShoppingListItem]:
    with session_scope() as session:
        row = session.get(ShoppingListItemORM, item_id)
        if row is None:
            return None
        return _to_model(row)


__all__ = [
    "list_shopping_items",
    "create_shopping_item",
    "update_shopping_item",
    "delete_shopping_item",
    "reset_shopping_list",
    "get_shopping_item",
]
