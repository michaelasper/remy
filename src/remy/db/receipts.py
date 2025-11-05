"""Receipt upload and OCR persistence helpers."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, text

from remy.models.receipt import Receipt, ReceiptOcrResult

from .models import ReceiptOcrResultORM, ReceiptORM
from .repository import session_scope


def _to_receipt_model(row: ReceiptORM) -> Receipt:
    return Receipt.model_validate(
        {
            "id": row.id,
            "filename": row.filename,
            "content_type": row.content_type,
            "size_bytes": row.size_bytes,
            "notes": row.notes,
            "uploaded_at": row.uploaded_at,
        }
    )


def _payload_to_dict(payload: Optional[str]) -> Optional[Dict[str, Any]]:
    if payload is None:
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return {"raw": payload}
    if isinstance(parsed, dict):
        return parsed
    return {"raw": parsed}


def _dict_to_payload(metadata: Optional[Dict[str, Any]]) -> Optional[str]:
    if metadata is None:
        return None
    return json.dumps(metadata, separators=(",", ":"), sort_keys=True)


def _to_ocr_model(row: ReceiptOcrResultORM) -> ReceiptOcrResult:
    return ReceiptOcrResult.model_validate(
        {
            "receipt_id": row.receipt_id,
            "status": row.status,
            "text": row.text,
            "confidence": row.confidence,
            "metadata": _payload_to_dict(row.payload),
            "error_message": row.error_message,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def _ensure_ocr_record(session, receipt_id: int) -> ReceiptOcrResultORM:
    record = session.get(ReceiptOcrResultORM, receipt_id)
    if record is None:
        record = ReceiptOcrResultORM(receipt_id=receipt_id, status="pending")
        session.add(record)
        session.flush()
    return record


def store_receipt(
    *,
    filename: str,
    content_type: Optional[str],
    content: bytes,
    notes: Optional[str] = None,
) -> Receipt:
    """Persist a raw receipt and return its metadata."""

    size_bytes = len(content)
    with session_scope() as session:
        _ensure_receipt_columns(session)
        record = ReceiptORM(
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            content=content,
            notes=notes,
        )
        session.add(record)
        session.flush()
        _ensure_ocr_record(session, record.id)
        return _to_receipt_model(record)


def list_receipts() -> List[Receipt]:
    """Return all stored receipts sorted by newest first."""

    with session_scope() as session:
        _ensure_receipt_columns(session)
        rows = (
            session.execute(select(ReceiptORM).order_by(ReceiptORM.uploaded_at.desc()))
            .scalars()
            .all()
        )
        return [_to_receipt_model(row) for row in rows]


def fetch_receipt(receipt_id: int) -> Receipt:
    """Return receipt metadata or raise if not found."""

    with session_scope() as session:
        _ensure_receipt_columns(session)
        record = session.get(ReceiptORM, receipt_id)
        if record is None:
            raise ValueError(f"Receipt {receipt_id} not found")
        return _to_receipt_model(record)


def fetch_receipt_blob(receipt_id: int) -> Tuple[Receipt, bytes]:
    """Return receipt metadata and raw bytes."""

    with session_scope() as session:
        _ensure_receipt_columns(session)
        record = session.get(ReceiptORM, receipt_id)
        if record is None:
            raise ValueError(f"Receipt {receipt_id} not found")
        metadata = _to_receipt_model(record)
        if record.content is not None:
            return metadata, bytes(record.content)
        if record.content_path:
            path = Path(record.content_path)
            if not path.exists():
                raise ValueError(f"Archived content missing for receipt {receipt_id}")
            with gzip.open(path, "rb") as handle:
                return metadata, handle.read()
        raise ValueError(f"Receipt {receipt_id} has no stored content")


def delete_receipt(receipt_id: int) -> None:
    """Delete a stored receipt."""

    with session_scope() as session:
        record = session.get(ReceiptORM, receipt_id)
        if record is None:
            raise ValueError(f"Receipt {receipt_id} not found")
        if record.content_path:
            path = Path(record.content_path)
            if path.exists():
                path.unlink()
        ocr_record = session.get(ReceiptOcrResultORM, receipt_id)
        if ocr_record is not None:
            session.delete(ocr_record)
        session.delete(record)


def claim_receipts_for_ocr(limit: int = 5) -> List[int]:
    """Mark up to `limit` pending receipts for processing and return their IDs."""

    with session_scope() as session:
        rows = (
            session.execute(
                select(ReceiptOcrResultORM)
                .where(ReceiptOcrResultORM.status.in_(("pending", "failed")))
                .order_by(ReceiptOcrResultORM.updated_at.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        claimed: List[int] = []
        for row in rows:
            row.status = "processing"
            session.flush()
            claimed.append(row.receipt_id)
        return claimed


def get_receipt_ocr(receipt_id: int) -> Optional[ReceiptOcrResult]:
    """Return OCR result metadata for a receipt, if present."""

    with session_scope() as session:
        receipt = session.get(ReceiptORM, receipt_id)
        if receipt is None:
            raise ValueError(f"Receipt {receipt_id} not found")
        record = session.get(ReceiptOcrResultORM, receipt_id)
        if record is None:
            record = _ensure_ocr_record(session, receipt_id)
        return _to_ocr_model(record)


def update_receipt_ocr(
    receipt_id: int,
    *,
    status: str,
    text: Optional[str] = None,
    confidence: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> ReceiptOcrResult:
    """Create or update OCR metadata for a receipt and return the latest view."""

    with session_scope() as session:
        record = _ensure_ocr_record(session, receipt_id)
        record.status = status
        record.text = text
        record.confidence = confidence
        record.payload = _dict_to_payload(metadata)
        record.error_message = error_message
        session.flush()
        session.refresh(record)
        return _to_ocr_model(record)


def offload_receipt_content(receipt_id: int, *, archive_dir: Path) -> Optional[Path]:
    """Persist receipt content to disk and clear the database blob."""

    archive_dir.mkdir(parents=True, exist_ok=True)
    with session_scope() as session:
        record = session.get(ReceiptORM, receipt_id)
        if record is None:
            raise ValueError(f"Receipt {receipt_id} not found")
        if record.content is None:
            if record.content_path:
                path = Path(record.content_path)
                return path
            return None

        digest = hashlib.sha256(record.content).hexdigest()[:16]
        target_path = archive_dir / f"receipt_{receipt_id}_{digest}.bin.gz"
        with gzip.open(target_path, "wb") as handle:
            handle.write(bytes(record.content))

        record.content = None
        record.content_path = str(target_path)
        session.flush()
        return target_path
def _ensure_receipt_columns(session) -> None:
    columns = session.execute(text("PRAGMA table_info(receipts)")).fetchall()
    column_names = {row[1] for row in columns}
    if "content" not in column_names:
        # Legacy schema; nothing to do since content column is required for earlier versions.
        return
    if "content_path" not in column_names:
        session.execute("ALTER TABLE receipts ADD COLUMN content_path TEXT")
    # SQLite cannot alter column nullability directly; new code handles NULL
    # content by reading from archived blobs when necessary.
