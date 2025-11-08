"""Meal plan output models."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Macros(BaseModel):
    """Macronutrient profile per serving."""

    kcal: Optional[float] = Field(default=None, ge=0)
    protein_g: Optional[float] = Field(default=None, ge=0)
    carb_g: Optional[float] = Field(default=None, ge=0)
    fat_g: Optional[float] = Field(default=None, ge=0)

    model_config = ConfigDict(frozen=True)


class IngredientRequirement(BaseModel):
    """Ingredient quantities required to execute a candidate."""

    ingredient_id: Optional[int] = Field(default=None, ge=0)
    name: str
    quantity_g: Optional[float] = Field(default=None, alias="qty_g", ge=0)
    quantity_ml: Optional[float] = Field(default=None, alias="qty_ml", ge=0)
    quantity_count: Optional[float] = Field(default=None, alias="qty_count", ge=0)

    model_config = ConfigDict(populate_by_name=True)


class InventoryDelta(BaseModel):
    """Inventory adjustment to apply when the meal is selected."""

    ingredient_id: int = Field(ge=0)
    use_g: Optional[float] = Field(default=None, ge=0)
    use_ml: Optional[float] = Field(default=None, ge=0)
    use_count: Optional[float] = Field(default=None, ge=0)

    model_config = ConfigDict(populate_by_name=True)


class ShoppingShortfall(BaseModel):
    """Ingredient shortfall requiring a purchase."""

    ingredient_id: Optional[int] = Field(default=None, ge=0)
    name: str
    need_g: Optional[float] = Field(default=None, ge=0)
    need_ml: Optional[float] = Field(default=None, ge=0)
    need_count: Optional[float] = Field(default=None, ge=0)
    reason: Optional[str] = Field(default=None)

    model_config = ConfigDict(frozen=True)


class PlanCandidate(BaseModel):
    """Single dinner candidate proposal."""

    title: str
    estimated_time_min: Optional[int] = Field(default=None, ge=0)
    servings: Optional[int] = Field(default=None, ge=1)
    steps: list[str] = Field(default_factory=list)
    ingredients_required: list[IngredientRequirement] = Field(default_factory=list)
    inventory_deltas: list[InventoryDelta] = Field(default_factory=list)
    shopping_shortfall: list[ShoppingShortfall] = Field(default_factory=list)
    macros_per_serving: Optional[Macros] = Field(default=None)
    diagnostics: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class Plan(BaseModel):
    """Complete plan for a given date."""

    date: date
    candidates: list[PlanCandidate] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)
