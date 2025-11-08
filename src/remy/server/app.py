"""ASGI application for Remy."""
# mypy: ignore-errors

from __future__ import annotations

import logging
from datetime import date
from importlib import resources
from time import perf_counter
from typing import Any, Optional
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import (
    Body,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field, ValidationError, model_validator

from remy import __version__, metrics
from remy.config import Settings, get_settings
from remy.db.receipts import update_receipt_ocr
from remy.ingest import ingest_receipt_items
from remy.logging_utils import configure_logging as configure_app_logging
from remy.models.context import (
    InventoryItem,
    LeftoverItem,
    PlanningContext,
    Preferences,
    RecentMeal,
)
from remy.models.plan import Plan, ShoppingShortfall
from remy.models.receipt import (
    InventorySuggestion as InventorySuggestionModel,
)
from remy.models.receipt import (
    Receipt,
    ReceiptLineItem,
    ReceiptOcrResult,
)
from remy.models.shopping import ShoppingListItem
from remy.ocr import ReceiptOcrService
from remy.ocr.worker import ReceiptOcrWorker
from remy.planner.context_builder import assemble_planning_context
from remy.server import deps, ui

logger = logging.getLogger(__name__)

MAX_RECEIPT_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MiB


def _json_safe(value: Any) -> Any:
    """Convert non-serializable values into JSON-safe representations."""

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    if isinstance(value, list):
        return [_json_safe(entry) for entry in value]
    if isinstance(value, tuple):
        return [_json_safe(entry) for entry in value]
    if isinstance(value, dict):
        return {key: _json_safe(sub_value) for key, sub_value in value.items()}
    return repr(value)


def _normalize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure validation error payloads can be serialized to JSON."""

    normalized: list[dict[str, Any]] = []
    for error in errors:
        normalized.append({key: _json_safe(value) for key, value in error.items()})
    return normalized


def _configure_logging(settings: Settings) -> None:
    secrets = [settings.api_token or "", settings.home_assistant_token or ""]
    configure_app_logging(settings.log_level, settings.log_format, secrets)


def create_app() -> FastAPI:
    """Create and configure a FastAPI application instance."""

    settings = get_settings()
    _configure_logging(settings)

    application = FastAPI(title="Remy Dinner Planner", version=__version__)

    static_dir = resources.files("remy.server.static")
    application.mount(
        "/static",
        StaticFiles(directory=str(static_dir)),
        name="static",
    )

    ocr_worker: ReceiptOcrWorker | None = None
    ocr_scheduler: AsyncIOScheduler | None = None
    if settings.ocr_worker_enabled:
        ocr_worker = ReceiptOcrWorker(
            service=ReceiptOcrService(lang=settings.ocr_default_lang),
            poll_interval=settings.ocr_worker_poll_interval,
            batch_size=settings.ocr_worker_batch_size,
            archive_dir=settings.ocr_archive_path,
        )
        ocr_scheduler = AsyncIOScheduler()
        ocr_scheduler.add_job(
            ocr_worker.poll_once,
            "interval",
            seconds=settings.ocr_worker_poll_interval,
            max_instances=1,
            coalesce=True,
        )

        @application.on_event("startup")
        async def start_ocr_worker() -> None:
            assert ocr_scheduler is not None
            ocr_worker.poll_once()
            ocr_scheduler.start()

        @application.on_event("shutdown")
        async def stop_ocr_worker() -> None:
            assert ocr_scheduler is not None
            ocr_scheduler.shutdown(wait=False)

    application.include_router(ui.router)
    logger.debug("Application created with log level %s", settings.log_level)

    if settings.log_requests:
        access_logger = logging.getLogger("remy.access")

        @application.middleware("http")
        async def log_request_response(request: Request, call_next):
            """Log request/response details without leaking sensitive data."""

            request_id = request.headers.get("X-Request-ID") or uuid4().hex
            request.state.request_id = request_id
            start = perf_counter()
            path = request.url.path
            method = request.method
            try:
                response: Response = await call_next(request)
            except Exception:
                duration_ms = (perf_counter() - start) * 1000
                access_logger.exception(
                    "HTTP %s %s status=500 duration_ms=%.2f",
                    request.method,
                    request.url.path,
                    duration_ms,
                    extra={"request_id": request_id},
                )
                metrics.REQUEST_COUNT.labels(method=method, path=path, status="500").inc()
                metrics.REQUEST_LATENCY.labels(method=method, path=path).observe(
                    duration_ms / 1000.0
                )
                raise

            duration_ms = (perf_counter() - start) * 1000
            response.headers.setdefault("X-Request-ID", request_id)
            access_logger.info(
                "HTTP %s %s status=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                extra={"request_id": request_id},
            )
            try:
                metrics.REQUEST_COUNT.labels(
                    method=method,
                    path=path,
                    status=str(response.status_code),
                ).inc()
                metrics.REQUEST_LATENCY.labels(method=method, path=path).observe(
                    duration_ms / 1000.0
                )
            except Exception:  # pragma: no cover - metrics best effort
                pass
            return response

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        body_preview: str | None = None
        try:
            raw_body = await request.body()
            if raw_body:
                decoded = raw_body.decode("utf-8", errors="replace")
                if len(decoded) > 2048:
                    decoded = decoded[:2048] + "...(truncated)"
                body_preview = decoded
        except Exception:  # pragma: no cover - defensive logging
            body_preview = "<unable to read body>"

        log_kwargs: dict[str, Any] = {}
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            log_kwargs["extra"] = {"request_id": request_id}

        logger.warning(
            "Validation error on %s %s: %s | body=%s",
            request.method,
            request.url.path,
            exc.errors(),
            body_preview,
            **log_kwargs,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": _normalize_validation_errors(exc.errors())},
        )

    @application.get(
        "/planning-context",
        response_model=PlanningContext,
        summary="Assemble planning context",
    )
    def planning_context_endpoint(
        context_date: Optional[date] = Query(default=None, alias="date"),
        attendees: Optional[int] = Query(default=None, ge=1),
        time_window: Optional[str] = Query(default=None, min_length=1, max_length=64),
        recent_meals: int = Query(default=14, ge=0, le=60),
        diet_override: Optional[str] = Query(default=None, min_length=1, max_length=255),
        allergens: Optional[list[str]] = Query(default=None),
        max_time_min: Optional[int] = Query(default=None, ge=0, le=240),
        preferred_cuisines: Optional[list[str]] = Query(default=None),
        recipe_search: Optional[bool] = Query(default=None),
        search_keywords: Optional[list[str]] = Query(default=None),
        auth: None = Depends(deps.require_api_token),
    ) -> PlanningContext:
        target_date = context_date or date.today()
        return assemble_planning_context(
            target_date=target_date,
            attendees=attendees,
            time_window=time_window,
            recent_meal_limit=recent_meals,
            diet_override=diet_override,
            allergens_override=allergens,
            max_time_override=max_time_min,
            preferred_cuisines=preferred_cuisines,
            recipe_search_enabled=recipe_search,
            recipe_search_keywords=search_keywords,
        )

    @application.post("/plan", response_model=Plan, summary="Generate dinner candidates")
    def generate_plan_endpoint(
        context: PlanningContext,
        auth: None = Depends(deps.require_api_token),
        plan_generator: deps.PlanGenerator = Depends(deps.get_plan_generator),
        shopping_list_provider: deps.ShoppingListProvider = Depends(deps.get_shopping_list_provider),
        shopping_list_creator: deps.ShoppingListCreator = Depends(deps.get_shopping_list_creator),
    ) -> Plan:
        """Generate candidate dinner plans from the provided context payload."""

        plan = plan_generator(context)
        try:
            _auto_add_shortfalls_to_shopping_list(plan, shopping_list_provider, shopping_list_creator)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Auto-add shopping shortfalls failed: %s", exc)
        return plan

    @application.get(
        "/inventory",
        response_model=list[InventoryItem],
        summary="List current inventory",
    )
    def inventory_list(
        provider: deps.InventoryProvider = Depends(deps.get_inventory_provider),
    ) -> list[InventoryItem]:
        return provider()

    @application.post(
        "/inventory",
        response_model=InventoryItem,
        status_code=status.HTTP_201_CREATED,
        summary="Create inventory item",
    )
    def inventory_create(
        payload: dict[str, Any] = Body(...),
        auth: None = Depends(deps.require_api_token),
        creator: deps.InventoryCreator = Depends(deps.get_inventory_creator),
    ) -> InventoryItem:
        try:
            parsed = InventoryCreateRequest.model_validate(payload)
        except ValidationError as exc:
            logger.warning("Invalid inventory create payload=%s errors=%s", payload, exc.errors())
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()
            ) from exc

        create_payload = parsed.model_dump()
        logger.debug("Creating inventory item payload=%s", create_payload)
        return creator(create_payload)

    @application.put(
        "/inventory/{item_id}",
        response_model=InventoryItem,
        summary="Update inventory item",
    )
    def inventory_update(
        item_id: int,
        payload: dict[str, Any] = Body(...),
        auth: None = Depends(deps.require_api_token),
        updater: deps.InventoryUpdater = Depends(deps.get_inventory_updater),
    ) -> InventoryItem:
        try:
            parsed = InventoryUpdateRequest.model_validate(payload)
        except ValidationError as exc:
            logger.warning(
                "Invalid inventory update payload=%s errors=%s (item_id=%s)",
                payload,
                exc.errors(),
                item_id,
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()
            ) from exc

        update_payload = parsed.model_dump(exclude_unset=True)
        logger.debug("Updating inventory item %s with payload=%s", item_id, update_payload)
        try:
            return updater(item_id, update_payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.delete(
        "/inventory/{item_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Delete inventory item",
    )
    def inventory_delete(
        item_id: int,
        auth: None = Depends(deps.require_api_token),
        deleter: deps.InventoryDeleter = Depends(deps.get_inventory_deleter),
    ) -> None:
        try:
            deleter(item_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.get(
        "/leftovers",
        response_model=list[LeftoverItem],
        summary="List tracked leftovers",
    )
    def leftovers_list(
        provider: deps.LeftoverProvider = Depends(deps.get_leftover_provider),
    ) -> list[LeftoverItem]:
        return provider()

    @application.post(
        "/leftovers",
        response_model=LeftoverItem,
        status_code=status.HTTP_201_CREATED,
        summary="Create leftover record",
    )
    def leftovers_create(
        payload: LeftoverCreateRequest = Body(...),
        auth: None = Depends(deps.require_api_token),
        creator: deps.LeftoverCreator = Depends(deps.get_leftover_creator),
    ) -> LeftoverItem:
        return creator(payload.model_dump())

    @application.put(
        "/leftovers/{leftover_id}",
        response_model=LeftoverItem,
        summary="Update leftover record",
    )
    def leftovers_update(
        leftover_id: int,
        payload: LeftoverUpdateRequest = Body(...),
        auth: None = Depends(deps.require_api_token),
        updater: deps.LeftoverUpdater = Depends(deps.get_leftover_updater),
    ) -> LeftoverItem:
        update_payload = payload.model_dump(exclude_unset=True)
        if not update_payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update",
            )
        try:
            return updater(leftover_id, update_payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.delete(
        "/leftovers/{leftover_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Delete leftover record",
    )
    def leftovers_delete(
        leftover_id: int,
        auth: None = Depends(deps.require_api_token),
        deleter: deps.LeftoverDeleter = Depends(deps.get_leftover_deleter),
    ) -> None:
        try:
            deleter(leftover_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.get(
        "/shopping-list",
        response_model=list[ShoppingListItem],
        summary="List shopping list items",
    )
    def shopping_list_list(
        provider: deps.ShoppingListProvider = Depends(deps.get_shopping_list_provider),
    ) -> list[ShoppingListItem]:
        return provider()

    @application.post(
        "/shopping-list",
        response_model=ShoppingListItem,
        status_code=status.HTTP_201_CREATED,
        summary="Create shopping list item",
    )
    def shopping_list_create(
        payload: ShoppingListCreateRequest = Body(...),
        auth: None = Depends(deps.require_api_token),
        creator: deps.ShoppingListCreator = Depends(deps.get_shopping_list_creator),
    ) -> ShoppingListItem:
        return creator(payload.model_dump())

    @application.put(
        "/shopping-list/{item_id}",
        response_model=ShoppingListItem,
        summary="Update shopping list item",
    )
    def shopping_list_update(
        item_id: int,
        payload: ShoppingListUpdateRequest = Body(...),
        auth: None = Depends(deps.require_api_token),
        updater: deps.ShoppingListUpdater = Depends(deps.get_shopping_list_updater),
    ) -> ShoppingListItem:
        update_payload = payload.model_dump(exclude_unset=True)
        if not update_payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update",
            )
        try:
            return updater(item_id, update_payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.delete(
        "/shopping-list/{item_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Delete shopping list item",
    )
    def shopping_list_delete(
        item_id: int,
        auth: None = Depends(deps.require_api_token),
        deleter: deps.ShoppingListDeleter = Depends(deps.get_shopping_list_deleter),
    ) -> None:
        try:
            deleter(item_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.post(
        "/shopping-list/reset",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Reset shopping list",
    )
    def shopping_list_reset(
        auth: None = Depends(deps.require_api_token),
        resetter: deps.ShoppingListResetter = Depends(deps.get_shopping_list_resetter),
    ) -> None:
        resetter()

    @application.post(
        "/shopping-list/{item_id}/add-to-inventory",
        response_model=InventoryItem,
        status_code=status.HTTP_201_CREATED,
        summary="Convert shopping item into inventory",
    )
    def shopping_list_add_to_inventory(
        item_id: int,
        payload: ShoppingListAddToInventoryRequest | None = Body(default=None),
        auth: None = Depends(deps.require_api_token),
        fetcher: deps.ShoppingListFetcher = Depends(deps.get_shopping_list_fetcher),
        deleter: deps.ShoppingListDeleter = Depends(deps.get_shopping_list_deleter),
        inventory_creator: deps.InventoryCreator = Depends(deps.get_inventory_creator),
    ) -> InventoryItem:
        item = fetcher(item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

        overrides = payload.model_dump(exclude_unset=True) if payload else {}
        name = overrides.get("name") or item.name
        quantity = overrides.get("quantity") or item.quantity
        if quantity is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity is required to add an item to inventory",
            )
        unit = overrides.get("unit") or item.unit or "ea"
        best_before = overrides.get("best_before")
        notes = overrides.get("notes") or item.notes

        create_payload: dict[str, Any] = {
            "name": name,
            "quantity": quantity,
            "unit": unit,
        }
        if best_before is not None:
            create_payload["best_before"] = best_before
        if notes:
            create_payload["notes"] = notes

        inventory_item = inventory_creator(create_payload)
        try:
            deleter(item_id)
        except ValueError:
            logger.warning(
                "Shopping list item %s vanished before deletion during add-to-inventory",
                item_id,
            )
        return inventory_item

    @application.get(
        "/preferences",
        response_model=Preferences,
        summary="Get household preferences",
    )
    def preferences_get(
        provider: deps.PreferencesProvider = Depends(deps.get_preferences_provider),
    ) -> Preferences:
        return provider()

    @application.put(
        "/preferences",
        response_model=Preferences,
        summary="Update household preferences",
    )
    def preferences_update(
        payload: dict[str, Any] = Body(...),
        auth: None = Depends(deps.require_api_token),
        provider: deps.PreferencesProvider = Depends(deps.get_preferences_provider),
        saver: deps.PreferencesSaver = Depends(deps.get_preferences_saver),
    ) -> Preferences:
        try:
            parsed = PreferencesUpdateRequest.model_validate(payload)
        except ValidationError as exc:
            logger.warning("Invalid preferences payload=%s errors=%s", payload, exc.errors())
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()
            ) from exc

        current = provider()
        update_data = parsed.model_dump(exclude_unset=True)
        if "allergens" in update_data and update_data["allergens"] is None:
            update_data["allergens"] = []
        logger.debug(
            "Updating preferences from current=%s with update=%s", current.model_dump(), update_data
        )
        merged = current.model_copy(update=update_data)
        return saver(merged)

    @application.get(
        "/receipts",
        response_model=list[Receipt],
        summary="List uploaded receipts",
    )
    def receipts_list(
        provider: deps.ReceiptListProvider = Depends(deps.get_receipt_list_provider),
    ) -> list[Receipt]:
        return provider()

    @application.post(
        "/receipts",
        response_model=Receipt,
        status_code=status.HTTP_201_CREATED,
        summary="Upload a receipt for processing",
    )
    async def receipts_upload(
        file: UploadFile = File(...),
        notes: Optional[str] = Form(default=None),
        auth: None = Depends(deps.require_api_token),
        storer: deps.ReceiptStorer = Depends(deps.get_receipt_storer),
    ) -> Receipt:
        filename = file.filename or "receipt"
        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty."
            )
        if len(content) > MAX_RECEIPT_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Receipt exceeds {MAX_RECEIPT_UPLOAD_BYTES // (1024 * 1024)} MiB limit.",
            )
        sanitized_notes = notes.strip() if notes and notes.strip() else None
        receipt = storer(
            filename,
            file.content_type,
            content,
            sanitized_notes,
        )
        logger.debug("Stored receipt id=%s filename=%s size=%s", receipt.id, filename, len(content))
        return receipt

    @application.get(
        "/receipts/{receipt_id}",
        response_model=Receipt,
        summary="Retrieve receipt metadata",
    )
    def receipts_get(
        receipt_id: int,
        fetcher: deps.ReceiptFetcher = Depends(deps.get_receipt_fetcher),
    ) -> Receipt:
        try:
            return fetcher(receipt_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.get(
        "/receipts/{receipt_id}/download",
        summary="Download a receipt file",
    )
    def receipts_download(
        receipt_id: int,
        fetcher: deps.ReceiptBlobFetcher = Depends(deps.get_receipt_blob_fetcher),
    ) -> Response:
        try:
            receipt, blob = fetcher(receipt_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        media_type = receipt.content_type or "application/octet-stream"
        headers = {"Content-Disposition": f'attachment; filename="{receipt.filename}"'}
        return Response(content=blob, media_type=media_type, headers=headers)

    @application.delete(
        "/receipts/{receipt_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Delete a stored receipt",
    )
    def receipts_delete(
        receipt_id: int,
        auth: None = Depends(deps.require_api_token),
        deleter: deps.ReceiptDeleter = Depends(deps.get_receipt_deleter),
    ) -> None:
        try:
            deleter(receipt_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.get(
        "/receipts/{receipt_id}/ocr",
        response_model=ReceiptOcrResult,
        summary="Retrieve OCR status for a receipt",
    )
    def receipts_ocr_status(
        receipt_id: int,
        provider: deps.ReceiptOcrStatusProvider = Depends(deps.get_receipt_ocr_status_provider),
    ) -> ReceiptOcrResult:
        try:
            return provider(receipt_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.post(
        "/receipts/{receipt_id}/ocr",
        response_model=ReceiptOcrResult,
        summary="Run OCR processing for a receipt",
    )
    def receipts_ocr_process(
        receipt_id: int,
        auth: None = Depends(deps.require_api_token),
        processor: deps.ReceiptOcrProcessor = Depends(deps.get_receipt_ocr_processor),
    ) -> ReceiptOcrResult:
        try:
            return processor(receipt_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.post(
        "/receipts/{receipt_id}/ingest",
        summary="Approve OCR items into inventory",
    )
    def receipts_ingest(
        receipt_id: int,
        request_payload: "ReceiptIngestRequest",
        auth: None = Depends(deps.require_api_token),
        ocr_provider: deps.ReceiptOcrStatusProvider = Depends(
            deps.get_receipt_ocr_status_provider
        ),
    ) -> dict[str, Any]:
        if not request_payload.items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide at least one item to ingest.",
            )

        try:
            ocr_result = ocr_provider(receipt_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        metadata = ocr_result.metadata.copy() if ocr_result.metadata else {}
        existing_ingested: list[dict[str, Any]] = metadata.get("ingested", [])
        existing_suggestions: list[dict[str, Any]] = metadata.get("suggestions", [])

        ingestion_payload = [
            {
                "name": item.name,
                "quantity": item.quantity,
                "unit": item.unit,
                "inventory_match_id": item.inventory_match_id,
                "notes": item.notes,
            }
            for item in request_payload.items
        ]

        ingestion_result = ingest_receipt_items(
            receipt_id,
            ingestion_payload,
            create_missing=False,
        )

        metadata["ingested"] = existing_ingested + ingestion_result["metadata_ingested"]
        metadata["suggestions"] = existing_suggestions + ingestion_result["metadata_suggestions"]
        update_receipt_ocr(
            receipt_id,
            status=ocr_result.status,
            text=ocr_result.text,
            confidence=ocr_result.confidence,
            metadata=metadata,
        )

        return {
            "ingested": ingestion_result["ingested"],
            "skipped": ingestion_result["skipped"],
            "suggestions": ingestion_result["suggestions"],
        }

    @application.get(
        "/inventory/suggestions",
        response_model=list[InventorySuggestionModel],
        summary="List pending inventory suggestions",
    )
    def inventory_suggestions_list(
        provider: deps.InventorySuggestionProvider = Depends(
            deps.get_inventory_suggestion_provider
        ),
    ) -> list[InventorySuggestionModel]:
        return provider()

    @application.post(
        "/inventory/suggestions/{suggestion_id}/approve",
        response_model=ReceiptLineItem,
        summary="Approve an inventory suggestion",
    )
    def inventory_suggestion_approve(
        suggestion_id: int,
        payload: "InventorySuggestionApproveRequest" = Body(...),
        auth: None = Depends(deps.require_api_token),
        approver: deps.InventorySuggestionApprover = Depends(
            deps.get_inventory_suggestion_approver
        ),
    ) -> ReceiptLineItem:
        try:
            return approver(
                suggestion_id,
                name=payload.name,
                quantity=payload.quantity,
                unit=payload.unit,
            )
        except ValueError as exc:
            message = str(exc)
            if "not found" in message:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from exc
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc

    @application.delete(
        "/inventory/suggestions/{suggestion_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Dismiss an inventory suggestion",
    )
    def inventory_suggestion_delete(
        suggestion_id: int,
        auth: None = Depends(deps.require_api_token),
        deleter: deps.InventorySuggestionDeleter = Depends(
            deps.get_inventory_suggestion_deleter
        ),
    ) -> None:
        try:
            deleter(suggestion_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @application.get("/metrics", include_in_schema=False)
    def metrics_endpoint() -> Response:
        payload = generate_latest()
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)

    @application.get(
        "/meals",
        response_model=list[RecentMeal],
        summary="List recorded meals",
    )
    def meals_list(
        provider: deps.MealsProvider = Depends(deps.get_meals_provider),
    ) -> list[RecentMeal]:
        return provider()

    @application.post(
        "/meals",
        response_model=RecentMeal,
        status_code=status.HTTP_201_CREATED,
        summary="Create or update a meal record",
    )
    def meals_upsert(
        payload: MealUpsertRequest,
        auth: None = Depends(deps.require_api_token),
        recorder: deps.MealRecorder = Depends(deps.get_meal_recorder),
    ) -> RecentMeal:
        meal = RecentMeal(
            date=payload.date,
            title=payload.title,
            rating=payload.rating,
            notes=payload.notes,
        )
        result = recorder(meal)
        return result

    @application.delete(
        "/meals",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Delete a meal record",
    )
    def meals_delete(
        meal_date: date = Query(alias="date"),
        title: str = Query(...),
        auth: None = Depends(deps.require_api_token),
        deleter: deps.MealDeleter = Depends(deps.get_meal_deleter),
    ) -> None:
        deleter(meal_date, title)

    return application


class ReceiptIngestItem(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    quantity: Optional[float] = Field(default=None, gt=0)
    unit: Optional[str] = Field(default=None, max_length=64)
    inventory_match_id: Optional[int] = Field(default=None, ge=1)
    notes: Optional[str] = Field(default=None, max_length=500)


class ReceiptIngestRequest(BaseModel):
    items: list[ReceiptIngestItem] = Field(default_factory=list, min_length=1)


class InventorySuggestionApproveRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    quantity: Optional[float] = Field(default=None, gt=0)
    unit: Optional[str] = Field(default=None, max_length=64)


class MealUpsertRequest(BaseModel):
    date: date
    title: str = Field(min_length=1, max_length=255)
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = Field(default=None, max_length=1000)


class InventoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    quantity: float = Field(gt=0)
    unit: str = Field(default="g", min_length=1, max_length=64)
    best_before: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class InventoryUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    quantity: Optional[float] = Field(default=None, gt=0)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=64)
    best_before: Optional[date] = Field(default=None)
    notes: Optional[str] = Field(default=None, max_length=500)


class LeftoverCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    quantity: float = Field(gt=0)
    unit: str = Field(default="g", min_length=1, max_length=64)
    best_before: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=1000)


class LeftoverUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    quantity: Optional[float] = Field(default=None, gt=0)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=64)
    best_before: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=1000)


class ShoppingListCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    quantity: Optional[float] = Field(default=None, gt=0)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=500)


class ShoppingListUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    quantity: Optional[float] = Field(default=None, gt=0)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=500)
    is_checked: Optional[bool] = Field(default=None)


class ShoppingListAddToInventoryRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    quantity: Optional[float] = Field(default=None, gt=0)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=64)
    best_before: Optional[date] = Field(default=None)
    notes: Optional[str] = Field(default=None, max_length=500)

ShoppingListCreateRequest.model_rebuild()
ShoppingListUpdateRequest.model_rebuild()
ShoppingListAddToInventoryRequest.model_rebuild()


def _auto_add_shortfalls_to_shopping_list(
    plan: Plan,
    list_provider: deps.ShoppingListProvider,
    list_creator: deps.ShoppingListCreator,
) -> None:
    shortfalls = [
        (candidate, shortfall)
        for candidate in plan.candidates
        for shortfall in (candidate.shopping_shortfall or [])
    ]
    if not shortfalls:
        return

    existing_items = list_provider()
    existing_names = {
        (item.name or "").strip().lower() for item in existing_items if (item.name or "").strip()
    }
    additions = 0

    for candidate, shortfall in shortfalls:
        name = (shortfall.name or "").strip()
        if not name:
            continue
        normalized = name.lower()
        if normalized in existing_names:
            continue

        quantity, unit = _shortfall_quantity_and_unit(shortfall)
        payload: dict[str, object] = {"name": name}
        if quantity is not None:
            payload["quantity"] = quantity
        if unit:
            payload["unit"] = unit
        notes = f"Plan shortfall ({plan.date}): {candidate.title}"
        payload["notes"] = notes[:500]

        try:
            list_creator(payload)
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.warning("Failed to add shopping shortfall '%s' to list: %s", name, exc)
            continue

        existing_names.add(normalized)
        additions += 1
        logger.info(
            "Shopping shortfall synced name=%s quantity=%s unit=%s plan=%s candidate=%s",
            name,
            payload.get("quantity"),
            payload.get("unit"),
            plan.date,
            candidate.title,
        )

    if additions:
        logger.info(
            "Auto-added %s shopping shortfall item(s) for plan %s",
            additions,
            plan.date,
        )


def _shortfall_quantity_and_unit(shortfall: ShoppingShortfall) -> tuple[Optional[float], Optional[str]]:
    if shortfall.need_g is not None:
        return float(shortfall.need_g), "g"
    if shortfall.need_ml is not None:
        return float(shortfall.need_ml), "ml"
    if shortfall.need_count is not None:
        return float(shortfall.need_count), "count"
    return None, None


class PreferencesUpdateRequest(BaseModel):
    diet: Optional[str] = Field(default=None, max_length=255)
    max_time_min: Optional[int] = Field(default=None, ge=0, le=240)
    allergens: Optional[list[str]] = None

    @model_validator(mode="before")
    @classmethod
    def coerce_allergens(cls, data: Any) -> Any:
        """Allow string-based allergens payloads for robustness."""
        if isinstance(data, dict) and "allergens" in data:
            allergens = data["allergens"]
            if isinstance(allergens, str):
                normalized = [
                    entry.strip()
                    for entry in allergens.split(",")
                    if isinstance(entry, str) and entry.strip()
                ]
                data["allergens"] = normalized
        return data


app = create_app()

__all__ = ["app", "create_app"]
