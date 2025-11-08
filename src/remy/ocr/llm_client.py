"""LLM helper for enhancing OCR receipt parsing."""
# mypy: ignore-errors

from __future__ import annotations

import json
import logging
import re
from typing import List, Sequence

import httpx

from remy.config import get_settings
from remy.models.receipt import ReceiptLineItem

LLM_TIMEOUT = 30.0
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

RECEIPT_SYSTEM_PROMPT = (
    "You are an expert grocery receipt parser. Read noisy OCR text and output a clean JSON object "
    "with line items suitable for pantry inventory tracking. Normalize product names (\"Organic "
    "Baby Spinach\" instead of \"ORG SPNCH\"). Extract approximate quantities, measurement units, "
    "and per-line totals when possible. If the OCR text lacks enough information, infer reasonable "
    "quantities (whole counts, pounds, etc.) and set confidence to 0.5. Never invent items that do "
    "not exist in the receipt. The schema:\n"
    '{\n'
    '  "items": [\n'
    '    {\n'
    '      "raw_text": "original line fragment",\n'
    '      "name": "clean friendly name",\n'
    '      "quantity": number|null,\n'
    '      "unit": "string|null",\n'
    '      "unit_price": number|null,\n'
    '      "total_price": number|null,\n'
    '      "confidence": number between 0 and 1\n'
    '    }\n'
    '  ]\n'
    '}\n'
    "Return only JSON."
)

RECEIPT_USER_PROMPT = (
    "Here is raw OCR text from a grocery receipt:\n"
    "```\n{ocr_text}\n```\n\n"
    "Heuristic parsing found these items (may be incomplete/noisy):\n"
    "{baseline_json}\n\n"
    "Reconcile the OCR text with those items. Improve names, fill missing quantities, and add any "
    "items the heuristics missed. Return strict JSON using the schema described earlier."
)

logger = logging.getLogger(__name__)


class ReceiptLLMClient:
    """Call an OpenAI/Ollama-compatible endpoint to enhance receipt line items."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        provider: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._provider = (provider or "openai").strip().lower()
        self._temperature = max(0.0, float(temperature))
        self._max_tokens = max(1, int(max_tokens))

    def parse_items(
        self,
        ocr_text: str,
        baseline_items: Sequence[ReceiptLineItem],
    ) -> List[ReceiptLineItem]:
        payload = self._build_payload(ocr_text, baseline_items)
        try:
            content = self._execute_chat(payload)
        except Exception:
            logger.exception("Receipt LLM request failed")
            raise

        json_blob = _extract_json_blob(content)
        try:
            parsed = json.loads(json_blob)
        except json.JSONDecodeError as exc:
            snippet = json_blob.strip().replace("\n", " ")[:200]
            raise ValueError(
                f"Receipt LLM returned invalid JSON: {exc}: payload={snippet}"
            ) from exc

        items_payload = parsed.get("items") or []
        enhanced: List[ReceiptLineItem] = []
        for entry in items_payload:
            item = self._coerce_line_item(entry)
            if item is not None:
                enhanced.append(item)
        return enhanced

    def _build_payload(
        self,
        ocr_text: str,
        baseline_items: Sequence[ReceiptLineItem],
    ) -> dict[str, object]:
        trimmed_text = ocr_text.strip()
        if len(trimmed_text) > 4000:
            trimmed_text = trimmed_text[:4000] + "\n...[truncated]"
        normalized_baseline = [
            {
                "raw_text": item.raw_text,
                "name": item.name,
                "quantity": item.quantity,
                "unit": item.unit,
                "total_price": item.total_price,
            }
            for item in list(baseline_items)[:20]
        ]
        baseline_json = json.dumps(normalized_baseline, ensure_ascii=False, indent=2)
        user_prompt = RECEIPT_USER_PROMPT.format(
            ocr_text=trimmed_text,
            baseline_json=baseline_json,
        )
        return {
            "system": RECEIPT_SYSTEM_PROMPT,
            "user": user_prompt,
        }

    def _execute_chat(self, prompt_payload: dict[str, object]) -> str:
        system = prompt_payload["system"]
        user = prompt_payload["user"]
        if self._provider == "ollama":
            endpoint = self._base_url
            if not endpoint.endswith("/api/chat"):
                endpoint = f"{endpoint}/api/chat"
            payload = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {
                    "temperature": self._temperature,
                    "num_predict": self._max_tokens,
                },
            }
            with httpx.Client(timeout=LLM_TIMEOUT) as client:
                response = client.post(endpoint, json=payload)
            response.raise_for_status()
            body = response.json()
            message = body.get("message") or {}
            content = (message.get("content") or "").strip()
            if not content:
                raise ValueError("Ollama receipt response did not include content.")
            return content

        endpoint = self._base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        payload = {
            "model": self._model,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        with httpx.Client(timeout=LLM_TIMEOUT) as client:
            response = client.post(endpoint, json=payload)
        response.raise_for_status()
        body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise ValueError("Receipt LLM returned no choices.")
        message = choices[0].get("message") or {}
        content = (message.get("content") or "").strip()
        if not content:
            raise ValueError("Receipt LLM returned an empty response.")
        return content

    @staticmethod
    def _coerce_line_item(entry: dict[str, object]) -> ReceiptLineItem | None:
        name = (entry.get("name") or "").strip()
        raw_text = (entry.get("raw_text") or name or "").strip()
        if not name and not raw_text:
            return None

        def _to_float(value) -> float | None:
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        return ReceiptLineItem(
            raw_text=raw_text or name,
            name=name or raw_text or "Unknown item",
            quantity=_to_float(entry.get("quantity")),
            unit=(entry.get("unit") or None),
            unit_price=_to_float(entry.get("unit_price")),
            total_price=_to_float(entry.get("total_price")),
            confidence=float(entry.get("confidence") or 0.85),
        )


def _extract_json_blob(text: str) -> str:
    match = _JSON_BLOCK_RE.search(text)
    if match:
        return match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1].strip()
    return text.strip()


def build_receipt_llm_client() -> ReceiptLLMClient | None:
    """Create an LLM client when receipt enhancements are enabled."""

    settings = get_settings()
    if not settings.receipt_llm_enabled:
        return None

    base_url = settings.receipt_llm_base_url or settings.planner_llm_base_url
    if not base_url:
        logger.debug("Receipt LLM enabled but no base URL configured.")
        return None

    provider = settings.receipt_llm_provider or settings.planner_llm_provider
    model = settings.receipt_llm_model or settings.planner_llm_model
    temperature = settings.receipt_llm_temperature
    max_tokens = settings.receipt_llm_max_tokens

    return ReceiptLLMClient(
        base_url=base_url,
        model=model,
        provider=provider,
        temperature=temperature,
        max_tokens=max_tokens,
    )


__all__ = ["ReceiptLLMClient", "build_receipt_llm_client"]
