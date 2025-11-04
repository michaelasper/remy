"""Planning context data models."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Preferences(BaseModel):
    """Household meal preferences and constraints."""

    diet: Optional[str] = Field(default=None)
    max_time_min: Optional[int] = Field(default=None)
    allergens: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class RecentMeal(BaseModel):
    """Record of a recently consumed meal."""

    date: date
    title: str
    rating: Optional[int] = Field(default=None, ge=1, le=5)

    model_config = ConfigDict(frozen=True)


class InventoryItem(BaseModel):
    """Item currently available in the household inventory."""

    id: int
    name: str
    quantity: float = Field(alias="qty")
    unit: str
    best_before: Optional[date] = Field(default=None)

    model_config = ConfigDict(frozen=True, populate_by_name=True)


class LeftoverItem(BaseModel):
    """Prepared leftovers tracked separately from inventory."""

    name: str
    quantity: float = Field(alias="qty")
    unit: str
    best_before: Optional[date] = Field(default=None)

    model_config = ConfigDict(frozen=True, populate_by_name=True)


class Constraints(BaseModel):
    """Additional situational constraints for the planning window."""

    attendees: Optional[int] = Field(default=None, ge=1)
    time_window: Optional[str] = Field(default=None)

    model_config = ConfigDict(frozen=True)


class PlanningContext(BaseModel):
    """Aggregated planning context shared with the planner agent."""

    date: date
    prefs: Preferences = Field(default_factory=Preferences)
    recent_meals: list[RecentMeal] = Field(default_factory=list)
    inventory: list[InventoryItem] = Field(default_factory=list)
    leftovers: list[LeftoverItem] = Field(default_factory=list)
    constraints: Constraints = Field(default_factory=Constraints)

    model_config = ConfigDict(populate_by_name=True)
