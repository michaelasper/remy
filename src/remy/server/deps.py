"""Dependency definitions for the Remy API server."""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from fastapi import Depends, HTTPException, Request, status

from remy.config import get_settings
from remy.db.inventory import (
    create_inventory_item,
    delete_inventory_item,
    list_inventory,
    update_inventory_item,
)
from remy.db.inventory_suggestions import (
    approve_suggestion,
    delete_suggestion,
    list_suggestions,
)
from remy.db.preferences import load_preferences, save_preferences
from remy.db.receipts import (
    delete_receipt,
    fetch_receipt,
    fetch_receipt_blob,
    get_receipt_ocr,
    list_receipts,
    store_receipt,
)
from remy.models.context import InventoryItem, PlanningContext, Preferences
from remy.models.plan import Plan
from remy.models.receipt import InventorySuggestion, Receipt, ReceiptLineItem, ReceiptOcrResult
from remy.ocr import ReceiptOcrService
from remy.planner.app.planner import generate_plan

PlanGenerator = Callable[[PlanningContext], Plan]
InventoryProvider = Callable[[], List[InventoryItem]]
InventoryCreator = Callable[[dict], InventoryItem]
InventoryUpdater = Callable[[int, dict], InventoryItem]
InventoryDeleter = Callable[[int], None]
PreferencesProvider = Callable[[], Preferences]
PreferencesSaver = Callable[[Preferences], Preferences]
ReceiptListProvider = Callable[[], List[Receipt]]
ReceiptStorer = Callable[[str, str | None, bytes, str | None], Receipt]
ReceiptFetcher = Callable[[int], Receipt]
ReceiptBlobFetcher = Callable[[int], Tuple[Receipt, bytes]]
ReceiptDeleter = Callable[[int], None]
ReceiptOcrStatusProvider = Callable[[int], ReceiptOcrResult]
ReceiptOcrProcessor = Callable[[int], ReceiptOcrResult]
InventorySuggestionProvider = Callable[[], List[InventorySuggestion]]
InventorySuggestionApprover = Callable[
    [int, Optional[str], Optional[float], Optional[str]],
    ReceiptLineItem,
]
InventorySuggestionDeleter = Callable[[int], None]


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


def get_receipt_list_provider() -> ReceiptListProvider:
    return list_receipts


def get_receipt_storer() -> ReceiptStorer:
    return lambda filename, content_type, content, notes=None: store_receipt(
        filename=filename,
        content_type=content_type,
        content=content,
        notes=notes,
    )


def get_receipt_fetcher() -> ReceiptFetcher:
    return fetch_receipt


def get_receipt_blob_fetcher() -> ReceiptBlobFetcher:
    return fetch_receipt_blob


def get_receipt_deleter() -> ReceiptDeleter:
    return delete_receipt


def get_receipt_ocr_status_provider() -> ReceiptOcrStatusProvider:
    return lambda receipt_id: get_receipt_ocr(receipt_id)


def get_receipt_ocr_processor() -> ReceiptOcrProcessor:
    settings = get_settings()
    service = ReceiptOcrService(lang=settings.ocr_default_lang)
    return service.process_receipt


def get_inventory_suggestion_provider() -> InventorySuggestionProvider:
    return list_suggestions


def get_inventory_suggestion_approver() -> InventorySuggestionApprover:
    return lambda suggestion_id, name=None, quantity=None, unit=None: approve_suggestion(
        suggestion_id,
        name=name,
        quantity=quantity,
        unit=unit,
    )


def get_inventory_suggestion_deleter() -> InventorySuggestionDeleter:
    return lambda suggestion_id: delete_suggestion(suggestion_id)


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
