"""Application configuration helpers."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

ENV_FILE_CANDIDATES = (Path(".env"), Path(".env.local"))


class Settings(BaseModel):
    """Global application settings loaded from environment variables or .env files."""

    database_path: Path = Field(
        default=Path("./data/remy.db"),
        description="SQLite database location.",
    )
    home_assistant_base_url: Optional[str] = Field(
        default=None,
        description="Home Assistant base URL.",
    )
    home_assistant_token: Optional[str] = Field(
        default=None,
        description="Long-lived access token.",
    )
    api_token: Optional[str] = Field(
        default=None,
        description="Bearer token required for authenticated endpoints.",
    )
    log_level: str = Field(default="INFO", description="Logging level (DEBUG/INFO/WARNING/ERROR)")
    log_format: str = Field(
        default="plain",
        description="Logging format (plain/json).",
    )
    log_requests: bool = Field(
        default=True,
        description="Emit request access logs when true.",
    )
    ocr_worker_enabled: bool = Field(
        default=False,
        description="Run the background OCR worker when true.",
    )
    ocr_worker_poll_interval: float = Field(
        default=5.0,
        description="Seconds between OCR worker polling iterations.",
    )
    ocr_worker_batch_size: int = Field(
        default=5,
        description="Maximum number of receipts to claim per OCR worker iteration.",
    )
    ocr_default_lang: str = Field(
        default="eng",
        description="Default Tesseract language code for OCR processing.",
    )
    ocr_archive_path: Path = Field(
        default=Path("./data/receipts_archive"),
        description="Directory used to store archived receipt blobs after OCR.",
    )
    planner_llm_base_url: Optional[str] = Field(
        default=None,
        description="Planner LLM base URL (OpenAI-compatible runtime such as llama.cpp, vLLM, etc.).",
    )
    planner_llm_model: str = Field(
        default="Qwen/Qwen1.5-0.5B-Chat",
        description="Model identifier passed to the planner LLM endpoint.",
    )
    planner_llm_temperature: float = Field(
        default=0.2,
        description="Sampling temperature for LLM-based planning.",
    )
    planner_llm_max_tokens: int = Field(
        default=1024,
        description="Maximum tokens to request from the planner LLM.",
    )
    planner_llm_provider: str = Field(
        default="openai",
        description="Planner LLM provider (openai or ollama).",
    )
    planner_enable_recipe_search: bool = Field(
        default=False,
        description="When true, augment planner prompt with live recipe search snippets.",
    )
    planner_recipe_search_results: int = Field(
        default=5,
        description="Number of recipe search snippets to include in the planner prompt.",
    )
    receipt_llm_enabled: bool = Field(
        default=False,
        description="Enable LLM-assisted receipt parsing when true.",
    )
    receipt_llm_base_url: Optional[str] = Field(
        default=None,
        description="Receipt parsing LLM base URL (falls back to planner URL when unset).",
    )
    receipt_llm_model: str = Field(
        default="Qwen/Qwen1.5-0.5B-Chat",
        description="Model identifier for receipt parsing LLM calls.",
    )
    receipt_llm_temperature: float = Field(
        default=0.0,
        description="Sampling temperature for receipt parsing LLM.",
    )
    receipt_llm_max_tokens: int = Field(
        default=400,
        description="Max tokens for receipt parsing LLM responses.",
    )
    receipt_llm_provider: str = Field(
        default="openai",
        description="Receipt parsing LLM provider (openai or ollama).",
    )
    rag_enabled: bool = Field(
        default=False,
        description="Enable im2recipe RAG enrichment when true.",
    )
    rag_model_path: Path = Field(
        default=Path("./data/models/im2recipe_model.t7"),
        description="Location where the im2recipe Torch7 model will be stored.",
    )
    rag_corpus_path: Path = Field(
        default=Path("./data/rag/recipes_seed.json"),
        description="JSON corpus used for retrieval-augmented prompt snippets.",
    )
    rag_top_k: int = Field(
        default=3,
        description="Number of RAG hits to surface in planner prompts.",
    )
    rag_embedding_dim: int = Field(
        default=384,
        description="Feature hashing dimension for the RAG vectorizer.",
    )

    model_config = ConfigDict(frozen=True)


def _coerce_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_env_file(path: Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, raw_value = line.split("=", 1)
                payload[key.strip()] = raw_value.strip()
    except FileNotFoundError:
        return {}
    return payload


def _load_env_file_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for candidate in ENV_FILE_CANDIDATES:
        values.update(_parse_env_file(candidate))
    return values


def _load_from_env() -> dict[str, object]:
    """Load optional overrides from env vars (with .env fallbacks)."""

    file_values = _load_env_file_values()

    def _env(key: str) -> Optional[str]:
        return os.environ.get(key) or file_values.get(key)

    payload: dict[str, object] = {}
    if (db_path := _env("REMY_DATABASE_PATH")):
        payload["database_path"] = Path(db_path)
    if (ha_url := _env("REMY_HOME_ASSISTANT_BASE_URL")):
        payload["home_assistant_base_url"] = ha_url
    if (ha_token := _env("REMY_HOME_ASSISTANT_TOKEN")):
        payload["home_assistant_token"] = ha_token
    if (api_token := _env("REMY_API_TOKEN")):
        payload["api_token"] = api_token
    if (log_level := _env("REMY_LOG_LEVEL")):
        payload["log_level"] = log_level
    if (log_format := _env("REMY_LOG_FORMAT")):
        payload["log_format"] = log_format
    if (log_requests := _env("REMY_LOG_REQUESTS")):
        payload["log_requests"] = _coerce_bool(log_requests)
    if (ocr_worker_enabled := _env("REMY_OCR_WORKER_ENABLED")):
        payload["ocr_worker_enabled"] = _coerce_bool(ocr_worker_enabled)
    if (ocr_worker_poll_interval := _env("REMY_OCR_WORKER_POLL_INTERVAL")):
        try:
            payload["ocr_worker_poll_interval"] = float(ocr_worker_poll_interval)
        except ValueError:
            pass
    if (ocr_worker_batch_size := _env("REMY_OCR_WORKER_BATCH_SIZE")):
        try:
            payload["ocr_worker_batch_size"] = int(ocr_worker_batch_size)
        except ValueError:
            pass
    if (ocr_lang := _env("REMY_OCR_LANG")):
        payload["ocr_default_lang"] = ocr_lang
    if (archive_path := _env("REMY_OCR_ARCHIVE_PATH")):
        payload["ocr_archive_path"] = Path(archive_path)
    llm_base_url = _env("REMY_LLM_BASE_URL") or _env("REMY_VLLM_BASE_URL")
    if llm_base_url:
        payload["planner_llm_base_url"] = llm_base_url
    if (planner_llm_model := _env("REMY_LLM_MODEL") or _env("REMY_VLLM_MODEL")):
        payload["planner_llm_model"] = planner_llm_model
    if (planner_llm_temperature := _env("REMY_LLM_TEMPERATURE") or _env("REMY_VLLM_TEMPERATURE")):
        try:
            payload["planner_llm_temperature"] = float(planner_llm_temperature)
        except ValueError:
            pass
    if (planner_llm_max_tokens := _env("REMY_LLM_MAX_TOKENS") or _env("REMY_VLLM_MAX_TOKENS")):
        try:
            payload["planner_llm_max_tokens"] = int(planner_llm_max_tokens)
        except ValueError:
            pass
    if (planner_llm_provider := _env("REMY_LLM_PROVIDER")):
        payload["planner_llm_provider"] = planner_llm_provider
    if (recipe_search_enabled := _env("REMY_RECIPE_SEARCH_ENABLED")):
        payload["planner_enable_recipe_search"] = _coerce_bool(recipe_search_enabled)
    if (recipe_search_results := _env("REMY_RECIPE_SEARCH_RESULTS")):
        try:
            payload["planner_recipe_search_results"] = int(recipe_search_results)
        except ValueError:
            pass
    if (receipt_llm_enabled := _env("REMY_RECEIPT_LLM_ENABLED")):
        payload["receipt_llm_enabled"] = _coerce_bool(receipt_llm_enabled)
    if (receipt_llm_base := _env("REMY_RECEIPT_LLM_BASE_URL")):
        payload["receipt_llm_base_url"] = receipt_llm_base
    if (receipt_llm_model := _env("REMY_RECEIPT_LLM_MODEL")):
        payload["receipt_llm_model"] = receipt_llm_model
    if (receipt_llm_temperature := _env("REMY_RECEIPT_LLM_TEMPERATURE")):
        try:
            payload["receipt_llm_temperature"] = float(receipt_llm_temperature)
        except ValueError:
            pass
    if (receipt_llm_max_tokens := _env("REMY_RECEIPT_LLM_MAX_TOKENS")):
        try:
            payload["receipt_llm_max_tokens"] = int(receipt_llm_max_tokens)
        except ValueError:
            pass
    if (receipt_llm_provider := _env("REMY_RECEIPT_LLM_PROVIDER")):
        payload["receipt_llm_provider"] = receipt_llm_provider
    if (rag_enabled := _env("REMY_RAG_ENABLED")):
        payload["rag_enabled"] = _coerce_bool(rag_enabled)
    if (rag_model_path := _env("REMY_RAG_MODEL_PATH")):
        payload["rag_model_path"] = Path(rag_model_path)
    if (rag_corpus_path := _env("REMY_RAG_CORPUS_PATH")):
        payload["rag_corpus_path"] = Path(rag_corpus_path)
    if (rag_top_k := _env("REMY_RAG_TOP_K")):
        try:
            payload["rag_top_k"] = int(rag_top_k)
        except ValueError:
            pass
    if (rag_dim := _env("REMY_RAG_EMBEDDING_DIM")):
        try:
            payload["rag_embedding_dim"] = int(rag_dim)
        except ValueError:
            pass
    return payload


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings(**_load_from_env())
