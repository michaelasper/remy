"""Dependency definitions for the Remy API server."""

from __future__ import annotations

from typing import Callable, List

from fastapi import Depends, HTTPException, Request, status

from remy.config import get_settings
from remy.db.inventory import (
    create_inventory_item,
    delete_inventory_item,
    list_inventory,
    update_inventory_item,
)
from remy.db.preferences import load_preferences, save_preferences
from remy.models.context import InventoryItem, PlanningContext, Preferences
from remy.models.plan import Plan
from remy.planner.app.planner import generate_plan

PlanGenerator = Callable[[PlanningContext], Plan]
InventoryProvider = Callable[[], List[InventoryItem]]
InventoryCreator = Callable[[dict], InventoryItem]
InventoryUpdater = Callable[[int, dict], InventoryItem]
InventoryDeleter = Callable[[int], None]
PreferencesProvider = Callable[[], Preferences]
PreferencesSaver = Callable[[Preferences], Preferences]


def get_plan_generator() -> PlanGenerator:
    """Return the default plan generator implementation."""

    return generate_plan


def get_inventory_provider() -> InventoryProvider:
    """Return the current inventory provider implementation."""

    return lambda: list_inventory()


def get_inventory_creator() -> InventoryCreator:
    return lambda payload: create_inventory_item(**payload)


def get_inventory_updater() -> InventoryUpdater:
    return lambda item_id, payload: update_inventory_item(item_id, **payload)


def get_inventory_deleter() -> InventoryDeleter:
    return lambda item_id: delete_inventory_item(item_id)


def get_preferences_provider() -> PreferencesProvider:
    return load_preferences


def get_preferences_saver() -> PreferencesSaver:
    return save_preferences


def require_api_token(
    request: Request,
    settings = Depends(get_settings),
) -> None:
    """Ensure requests carry the configured API token when required."""

    token = settings.api_token
    if not token:
        return

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.split("Bearer ")[-1].strip() == token:
        return

    if request.headers.get("X-API-Key") == token:
        return

    if request.query_params.get("api_token") == token:
        return

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
