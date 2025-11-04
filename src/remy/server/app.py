"""ASGI application for Remy."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from remy import __version__
from remy.config import get_settings
from remy.models.context import InventoryItem, PlanningContext, Preferences
from remy.models.plan import Plan
from remy.server import deps, ui


def _configure_logging(level_name: str) -> None:
    numeric_level = getattr(logging, level_name.upper(), logging.INFO)
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=numeric_level,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
    else:
        root_logger.setLevel(numeric_level)
    logging.getLogger("uvicorn").setLevel(numeric_level)


def create_app() -> FastAPI:
    """Create and configure a FastAPI application instance."""

    settings = get_settings()
    _configure_logging(settings.log_level)

    application = FastAPI(title="Remy Dinner Planner", version=__version__)

    application.include_router(ui.router)

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
        payload: InventoryCreateRequest,
        auth: None = Depends(deps.require_api_token),
        creator: deps.InventoryCreator = Depends(deps.get_inventory_creator),
    ) -> InventoryItem:
        return creator(payload.model_dump())

    @application.put(
        "/inventory/{item_id}",
        response_model=InventoryItem,
        summary="Update inventory item",
    )
    def inventory_update(
        item_id: int,
        payload: InventoryUpdateRequest,
        auth: None = Depends(deps.require_api_token),
        updater: deps.InventoryUpdater = Depends(deps.get_inventory_updater),
    ) -> InventoryItem:
        try:
            return updater(item_id, payload.model_dump(exclude_unset=True))
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
        payload: PreferencesUpdateRequest,
        auth: None = Depends(deps.require_api_token),
        provider: deps.PreferencesProvider = Depends(deps.get_preferences_provider),
        saver: deps.PreferencesSaver = Depends(deps.get_preferences_saver),
    ) -> Preferences:
        current = provider()
        update_data = payload.model_dump(exclude_unset=True)
        if "allergens" in update_data and update_data["allergens"] is None:
            update_data["allergens"] = []
        merged = current.model_copy(update=update_data)
        return saver(merged)

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
