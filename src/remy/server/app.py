"""ASGI application for Remy."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from remy import __version__
from remy.models.context import InventoryItem, PlanningContext
from remy.models.plan import Plan
from remy.server import deps, ui


def create_app() -> FastAPI:
    """Create and configure a FastAPI application instance."""

    application = FastAPI(title="Remy Dinner Planner", version=__version__)

    application.include_router(ui.router)

    @application.post("/plan", response_model=Plan, summary="Generate dinner candidates")
    def generate_plan_endpoint(
        context: PlanningContext,
        plan_generator: deps.PlanGenerator = Depends(deps.get_plan_generator),
    ) -> Plan:
        """Generate candidate dinner plans from the provided context payload."""

        return plan_generator(context)

    @application.get(
        "/inventory",
        response_model=list[InventoryItem],
        summary="List current inventory",
    )
    def inventory_endpoint(
        provider: deps.InventoryProvider = Depends(deps.get_inventory_provider),
    ) -> list[InventoryItem]:
        """Return all known inventory items."""

        return provider()

    return application


app = create_app()

__all__ = ["app", "create_app"]
