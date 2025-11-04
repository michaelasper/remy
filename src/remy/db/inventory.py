"""Inventory data access helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from remy.config import get_settings
from remy.models.context import InventoryItem

DEFAULT_INVENTORY = [
    {"id": 1, "name": "chicken thigh, boneless", "qty": 600, "unit": "g"},
    {"id": 2, "name": "broccoli", "qty": 400, "unit": "g"},
    {"id": 3, "name": "brown rice", "qty": 750, "unit": "g"},
]


def _default_snapshot_path() -> Path:
    settings = get_settings()
    db_path = settings.database_path
    return db_path.parent / "inventory_snapshot.json"


def load_inventory(snapshot_path: Path | None = None) -> List[InventoryItem]:
    """
    Load inventory records from a JSON snapshot file.

    The snapshot path defaults to `<database_dir>/inventory_snapshot.json`.
    """
    path = snapshot_path or _default_snapshot_path()
    if path.exists():
        data: Iterable[dict[str, object]] = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = DEFAULT_INVENTORY
    return [InventoryItem.model_validate(item) for item in data]
