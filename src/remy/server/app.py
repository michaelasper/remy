"""ASGI application for Remy."""

from __future__ import annotations

import logging
from datetime import date
from time import perf_counter
from typing import Any, Optional
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError, model_validator

from remy import __version__
from remy.config import Settings, get_settings
from remy.logging_utils import configure_logging as configure_app_logging
from remy.models.context import InventoryItem, PlanningContext, Preferences
from remy.models.plan import Plan
from remy.models.receipt import Receipt, ReceiptOcrResult
from remy.ocr import ReceiptOcrService
from remy.ocr.worker import ReceiptOcrWorker
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

    @application.post("/plan", response_model=Plan, summary="Generate dinner candidates")
    def generate_plan_endpoint(
        context: PlanningContext,
        auth: None = Depends(deps.require_api_token),
        plan_generator: deps.PlanGenerator = Depends(deps.get_plan_generator),
    ) -> Plan:
        """Generate candidate dinner plans from the provided context payload."""

        return plan_generator(context)

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

    return application


app = create_app()

__all__ = ["app", "create_app"]
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
