"""Pydantic models for receipt uploads."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Receipt(BaseModel):
    """Metadata describing an uploaded receipt."""

    id: int
    filename: str
    content_type: Optional[str] = None
    size_bytes: int
    notes: Optional[str] = None
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReceiptOcrResult(BaseModel):
    """OCR extraction state for a receipt."""

    receipt_id: int
    status: Literal["pending", "processing", "succeeded", "failed"]
    text: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReceiptLineItem(BaseModel):
    """Structured line item parsed from a receipt."""

    raw_text: str
    name: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    confidence: float = 0.0
    inventory_match_id: Optional[int] = None
    inventory_match_name: Optional[str] = None
    inventory_match_score: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class ReceiptStructuredData(BaseModel):
    """Structured, normalized view of a receipt."""

    store_name: Optional[str] = None
    purchase_date: Optional[date] = None
    currency: Optional[str] = None
    items: list[ReceiptLineItem] = Field(default_factory=list)
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)
