"""Shared helpers for planner modules."""

from __future__ import annotations

from typing import Dict, Iterable, Optional

from remy.models.context import InventoryItem, LeftoverItem


def normalize_name(value: str) -> str:
    """Normalize free-text names for comparison."""
    return " ".join(value.lower().split())


def build_inventory_index(inventory: Iterable[InventoryItem]) -> Dict[str, InventoryItem]:
    """Create a lookup table of inventory items by normalized name."""
    return {normalize_name(item.name): item for item in inventory}


def build_leftover_index(leftovers: Iterable[LeftoverItem]) -> Dict[str, LeftoverItem]:
    """Create a lookup table of leftovers by normalized name."""
    return {normalize_name(item.name): item for item in leftovers}


def resolve_inventory_item(
    normalized_name: str, index: Dict[str, InventoryItem]
) -> Optional[InventoryItem]:
    """Locate an inventory item by normalized name with loose matching."""
    if normalized_name in index:
        return index[normalized_name]
    for key, item in index.items():
        if normalized_name in key or key in normalized_name:
            return item
    return None


def resolve_leftover_item(
    normalized_name: str, index: Dict[str, LeftoverItem]
) -> Optional[LeftoverItem]:
    """Locate a leftover item by normalized name with loose matching."""
    if normalized_name in index:
        return index[normalized_name]
    for key, item in index.items():
        if normalized_name in key or key in normalized_name:
            return item
    return None
