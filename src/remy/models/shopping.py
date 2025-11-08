"""Shopping list models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ShoppingListItem(BaseModel):
    """Single entry on the household shopping list."""

    id: int
    name: str
    quantity: Optional[float] = Field(default=None)
    unit: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None, max_length=1000)
    is_checked: bool = Field(default=False)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(frozen=True)


__all__ = ["ShoppingListItem"]
