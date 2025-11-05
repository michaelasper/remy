"""Inventory suggestion persistence helpers."""

from __future__ import annotations

import math
from typing import List, Optional

from sqlalchemy import select

from remy.models.receipt import InventorySuggestion, ReceiptLineItem

from .inventory import create_inventory_item
from .models import InventorySuggestionORM
from .repository import session_scope


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().split())


def _to_model(row: InventorySuggestionORM) -> InventorySuggestion:
    return InventorySuggestion.model_validate(
        {
            "id": row.id,
            "receipt_id": row.receipt_id,
            "name": row.name,
            "normalized_name": row.normalized_name,
            "quantity": row.quantity,
            "unit": row.unit,
            "confidence": row.confidence,
            "notes": row.notes,
            "created_at": row.created_at,
        }
    )


def create_suggestion(
    *,
    receipt_id: int,
    name: str,
    quantity: Optional[float],
    unit: Optional[str],
    confidence: Optional[float] = None,
    notes: Optional[str] = None,
) -> InventorySuggestion:
    with session_scope() as session:
        record = InventorySuggestionORM(
            receipt_id=receipt_id,
            name=name,
            normalized_name=_normalize_name(name),
            quantity=quantity,
            unit=unit,
            confidence=confidence,
            notes=notes,
        )
        session.add(record)
        session.flush()
        session.refresh(record)
        return _to_model(record)


def list_suggestions() -> List[InventorySuggestion]:
    with session_scope() as session:
        rows = (
            session.execute(
                select(InventorySuggestionORM).order_by(InventorySuggestionORM.created_at.asc())
            )
            .scalars()
            .all()
        )
        return [_to_model(row) for row in rows]


def delete_suggestion(suggestion_id: int) -> None:
    with session_scope() as session:
        record = session.get(InventorySuggestionORM, suggestion_id)
        if record is None:
            raise ValueError(f"Inventory suggestion {suggestion_id} not found")
        session.delete(record)


def approve_suggestion(
    suggestion_id: int,
    *,
    name: Optional[str] = None,
    quantity: Optional[float] = None,
    unit: Optional[str] = None,
) -> ReceiptLineItem:
    with session_scope() as session:
        record = session.get(InventorySuggestionORM, suggestion_id)
        if record is None:
            raise ValueError(f"Inventory suggestion {suggestion_id} not found")

        final_name = name or record.name
        final_quantity = quantity if quantity is not None else record.quantity or 1.0
        if math.isfinite(final_quantity) is False or final_quantity <= 0:
            raise ValueError("Quantity must be positive for approval")
        final_unit = unit if unit is not None else record.unit or "count"

        item = create_inventory_item(
            name=final_name,
            quantity=final_quantity,
            unit=final_unit,
        )
        session.delete(record)
        return ReceiptLineItem(
            raw_text=record.name,
            name=item.name,
            quantity=final_quantity,
            unit=item.unit,
            unit_price=None,
            total_price=None,
            confidence=record.confidence or 0.0,
            inventory_match_id=item.id,
            inventory_match_name=item.name,
            inventory_match_score=None,
        )
