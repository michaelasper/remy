"""Shared helpers for turning parsed receipts into inventory updates."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from rapidfuzz import fuzz, process

from remy.db.inventory import create_inventory_item, list_inventory, update_inventory_item
from remy.db.inventory_suggestions import create_suggestion


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def ingest_receipt_items(
    receipt_id: int,
    items: List[Dict[str, Any]],
    *,
    create_missing: bool,
    confidence_threshold: float = 0.85,
) -> Dict[str, List[Dict[str, Any]]]:
    """Insert receipt-derived items into inventory or suggestion queues."""

    inventory = list_inventory()
    inventory_by_id = {item.id: item for item in inventory if item.id is not None}
    inventory_choices = [item.name for item in inventory if item.id is not None]

    ingested: List[Dict[str, Any]] = []
    metadata_ingested: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    suggestions: List[Dict[str, Any]] = []
    metadata_suggestions: List[Dict[str, Any]] = []

    for raw_item in items:
        name = (raw_item.get("name") or "").strip()
        if not name:
            skipped.append({"reason": "missing_name"})
            continue

        quantity = raw_item.get("quantity")
        unit = raw_item.get("unit")
        notes = raw_item.get("notes")
        match_id = raw_item.get("inventory_match_id")

        matched_item = None
        match_score: Optional[float] = None

        if match_id:
            matched_item = inventory_by_id.get(match_id)

        if matched_item is None and inventory_choices:
            match = process.extractOne(name, inventory_choices, scorer=fuzz.WRatio)
            if match:
                matched_name, score, index = match
                match_score = score / 100.0
                if match_score >= confidence_threshold and index is not None:
                    matched_item = inventory[index]

        if matched_item and match_score is not None and match_score < confidence_threshold:
            matched_item = None

        if matched_item is not None:
            if quantity is None:
                if create_missing:
                    quantity = 1.0
                else:
                    skipped.append({"name": name, "reason": "missing_quantity"})
                    continue
            updated = update_inventory_item(
                matched_item.id,
                {"quantity": float(matched_item.qty or 0.0) + float(quantity)},
            )
            ingested.append({"id": updated.id, "action": "updated", "name": updated.name})
            metadata_ingested.append({"name": updated.name, "quantity": quantity})
            inventory_by_id[updated.id] = updated
            continue

        if create_missing:
            resolved_quantity = float(quantity) if quantity is not None else 1.0
            resolved_unit = unit or "count"
            created = create_inventory_item(
                name=name,
                quantity=resolved_quantity,
                unit=resolved_unit,
            )
            ingested.append({"id": created.id, "action": "created", "name": created.name})
            metadata_ingested.append({"name": created.name, "quantity": resolved_quantity})
            inventory.append(created)
            inventory_by_id[created.id] = created
            inventory_choices.append(created.name)
        else:
            suggestion = create_suggestion(
                receipt_id=receipt_id,
                name=name,
                quantity=quantity,
                unit=unit,
                confidence=match_score,
                notes=notes,
            )
            suggestions.append({"id": suggestion.id, "name": suggestion.name})
            metadata_suggestions.append({"id": suggestion.id, "name": suggestion.name})

    return {
        "ingested": ingested,
        "metadata_ingested": metadata_ingested,
        "skipped": skipped,
        "suggestions": suggestions,
        "metadata_suggestions": metadata_suggestions,
    }


__all__ = ["ingest_receipt_items"]
