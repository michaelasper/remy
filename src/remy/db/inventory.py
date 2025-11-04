"""Inventory data access helpers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Iterable, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from remy.config import get_settings
from remy.models.context import InventoryItem

from .models import InventoryItemORM
from .repository import get_session, session_scope

DEFAULT_INVENTORY = [
    {"id": 1, "name": "chicken thigh, boneless", "qty": 600, "unit": "g"},
    {"id": 2, "name": "broccoli", "qty": 400, "unit": "g"},
    {"id": 3, "name": "brown rice", "qty": 750, "unit": "g"},
]


def _default_snapshot_path() -> Path:
    settings = get_settings()
    db_path = settings.database_path
    return db_path.parent / "inventory_snapshot.json"


def _load_snapshot_data(snapshot_path: Path | None = None) -> Iterable[dict[str, object]]:
    path = snapshot_path or _default_snapshot_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return DEFAULT_INVENTORY


def _seed_inventory(session: Session, snapshot_path: Path | None = None) -> None:
    exists = session.execute(select(InventoryItemORM.id).limit(1)).first()
    if exists:
        return

    for record in _load_snapshot_data(snapshot_path):
        best_before = record.get("best_before")
        if isinstance(best_before, str):
            try:
                best_before_date = date.fromisoformat(best_before)
            except ValueError:
                best_before_date = None
        else:
            best_before_date = best_before

        session.merge(
            InventoryItemORM(
                id=int(record.get("id")) if record.get("id") is not None else None,
                name=str(record["name"]),
                quantity=float(record.get("qty") or record.get("quantity", 0.0)),
                unit=str(record.get("unit") or ""),
                best_before=best_before_date,
            )
        )

    session.flush()


def _to_model(row: InventoryItemORM) -> InventoryItem:
    payload = {
        "id": row.id,
        "name": row.name,
        "qty": row.quantity,
        "unit": row.unit,
        "best_before": row.best_before,
    }
    if row.notes:
        payload["notes"] = row.notes
    return InventoryItem.model_validate(payload)


def list_inventory(snapshot_path: Path | None = None) -> List[InventoryItem]:
    """Return inventory items stored in the database (seeded from snapshot if empty)."""

    with session_scope() as session:
        _seed_inventory(session, snapshot_path)
        rows = (
            session.execute(select(InventoryItemORM).order_by(InventoryItemORM.name))
            .scalars()
            .all()
        )
        return [_to_model(row) for row in rows]


def save_inventory_item(item: InventoryItem) -> InventoryItem:
    """Insert or update a single inventory item."""

    with session_scope() as session:
        db_item = None
        if item.id is not None:
            db_item = session.get(InventoryItemORM, item.id)

        if db_item is None:
            db_item = InventoryItemORM(
                name=item.name,
                quantity=float(item.quantity),
                unit=item.unit,
                best_before=item.best_before,
            )
            session.add(db_item)
        else:
            db_item.name = item.name
            db_item.quantity = float(item.quantity)
            db_item.unit = item.unit
            db_item.best_before = item.best_before

        session.flush()
        return _to_model(db_item)


def raw_session() -> Session:
    """Expose a session for advanced operations (primarily testing)."""

    return get_session()
