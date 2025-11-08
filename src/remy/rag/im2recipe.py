"""Retrieval augmented generation helpers backed by the im2recipe model."""
# mypy: ignore-errors

from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import List, Sequence

import numpy as np
from annoy import AnnoyIndex

from remy.config import get_settings
from remy.models.context import PlanningContext

IM2RECIPE_URL = "http://wednesday.csail.mit.edu/pretrained/im2recipe_model.t7.gz"
_MODEL_LOCK = Lock()
_RAG_CACHE: "Im2RecipeRAG | None" = None


@dataclass(frozen=True)
class RecipeDocument:
    """Simple representation of a recipe used for retrieval."""

    title: str
    summary: str
    ingredients: tuple[str, ...]
    instructions: tuple[str, ...]
    source: str | None = None


def ensure_im2recipe_model(model_path: Path, *, source_url: str = IM2RECIPE_URL) -> Path:
    """Download and decompress the Torch7 model if it is not present."""

    model_path = model_path.expanduser()
    if model_path.exists():
        return model_path

    with _MODEL_LOCK:
        if model_path.exists():
            return model_path

        model_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_gz = model_path.with_suffix(model_path.suffix + ".download")
        with urllib.request.urlopen(source_url) as response, tmp_gz.open("wb") as target:
            shutil.copyfileobj(response, target)

        with gzip.open(tmp_gz, "rb") as src, model_path.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        tmp_gz.unlink(missing_ok=True)
        return model_path


class Im2RecipeRAG:
    """Feature-hashing retriever seeded by the pretrained im2recipe model bytes."""

    def __init__(
        self,
        *,
        model_path: Path,
        corpus_path: Path,
        embedding_dim: int = 384,
        index_path: Path | None = None,
        index_trees: int = 50,
    ) -> None:
        self.model_path = model_path
        self.corpus_path = corpus_path
        self.embedding_dim = int(max(64, embedding_dim))
        self.index_path = index_path
        self.index_trees = max(1, int(index_trees))
        self._model_digest = self._digest_file(model_path)
        self._documents = self._load_corpus(corpus_path)
        self._annoy_index: AnnoyIndex | None = None
        self._dense_index: np.ndarray | None = None
        self._prepare_indexes()

    @property
    def documents(self) -> Sequence[RecipeDocument]:
        return self._documents

    def retrieve(self, context: PlanningContext, *, top_k: int) -> list[RecipeDocument]:
        query_text = self._context_to_query(context)
        return self.retrieve_from_text(query_text, top_k=top_k)

    def retrieve_from_text(self, text: str, *, top_k: int) -> list[RecipeDocument]:
        if not self._documents:
            return []
        top_k = max(1, min(top_k, len(self._documents)))
        vector = self._embed_text(text)
        if self._annoy_index is not None:
            indices = self._annoy_index.get_nns_by_vector(vector.tolist(), top_k)
            return [self._documents[idx] for idx in indices]
        if self._dense_index is not None and self._dense_index.size:
            similarities = self._dense_index @ vector
            indices = np.argsort(similarities)[-top_k:][::-1]
            return [self._documents[idx] for idx in indices]
        return []

    def format_document(self, doc: RecipeDocument) -> str:
        ingredient_preview = ", ".join(doc.ingredients[:6])
        instructions_preview = " ".join(doc.instructions[:2])
        return (
            f"{doc.title} — {doc.summary} "
            f"Key ingredients: {ingredient_preview}. "
            f"First steps: {instructions_preview}"
        )

    def _prepare_indexes(self) -> None:
        if not self._documents:
            self._dense_index = np.zeros((0, self.embedding_dim), dtype=np.float32)
            return

        if self.index_path is not None:
            needs_rebuild = (
                not self.index_path.exists()
                or self.index_path.stat().st_mtime < self.corpus_path.stat().st_mtime
            )
            if needs_rebuild:
                self._annoy_index = self._build_annoy_index(self._documents)
                self.index_path.parent.mkdir(parents=True, exist_ok=True)
                if self._annoy_index.get_n_items() > 0:
                    self._annoy_index.save(str(self.index_path))
            else:
                self._annoy_index = self._load_annoy_index(self.index_path)
        if self._annoy_index is None:
            self._dense_index = self._build_dense_index(self._documents)

    def _build_dense_index(self, docs: Sequence[RecipeDocument]) -> np.ndarray:
        if not docs:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)

        vectors = np.stack(
            [self._embed_text(self._text_for_recipe(doc)) for doc in docs], axis=0
        )
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (vectors / norms).astype(np.float32)

    def _build_annoy_index(self, docs: Sequence[RecipeDocument]) -> AnnoyIndex:
        index = AnnoyIndex(self.embedding_dim, "angular")
        if not docs:
            index.build(1)
            return index
        for idx, doc in enumerate(docs):
            vector = self._embed_text(self._text_for_recipe(doc))
            index.add_item(idx, vector.tolist())
        index.build(self.index_trees)
        return index

    def _load_annoy_index(self, path: Path) -> AnnoyIndex:
        index = AnnoyIndex(self.embedding_dim, "angular")
        loaded = index.load(str(path))
        if not loaded:
            return self._build_annoy_index(self._documents)
        return index

    def _embed_text(self, text: str) -> np.ndarray:
        tokens = self._tokenize(text)
        vector = np.zeros(self.embedding_dim, dtype=np.float32)
        for token, freq in tokens.items():
            token_seed = hashlib.sha256(self._model_digest + token.encode("utf-8")).digest()
            bucket = int.from_bytes(token_seed[:4], "big") % self.embedding_dim
            sign = 1.0 if (token_seed[4] & 1) == 0 else -1.0
            vector[bucket] += sign * freq
        norm = np.linalg.norm(vector)
        if norm:
            vector /= norm
        return vector

    def _tokenize(self, text: str) -> dict[str, float]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        counts: dict[str, float] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0.0) + 1.0
        return counts

    def _context_to_query(self, context: PlanningContext) -> str:
        parts: list[str] = []
        if context.prefs.diet:
            parts.append(context.prefs.diet)
        if context.constraints.time_window:
            parts.append(context.constraints.time_window)
        if context.prefs.allergens:
            parts.extend(f"avoid_{allergen}" for allergen in context.prefs.allergens)
        for item in context.inventory:
            parts.append(f"{item.name} {item.quantity or 0}{item.unit}")
        for leftover in context.leftovers:
            parts.append(f"leftover {leftover.name}")
        for meal in context.recent_meals:
            parts.append(f"recent {meal.title}")
        return " ".join(parts)

    def _text_for_recipe(self, doc: RecipeDocument) -> str:
        ingredients = " ".join(doc.ingredients)
        instructions = " ".join(doc.instructions)
        return f"{doc.title} {doc.summary} {ingredients} {instructions}"

    def _load_corpus(self, path: Path) -> List[RecipeDocument]:
        data = json.loads(path.read_text(encoding="utf-8"))
        documents: List[RecipeDocument] = []
        for entry in data:
            documents.append(
                RecipeDocument(
                    title=entry.get("title", "Untitled recipe"),
                    summary=entry.get("summary", ""),
                    ingredients=tuple(entry.get("ingredients") or ()),
                    instructions=tuple(entry.get("instructions") or ()),
                    source=entry.get("source"),
                )
            )
        return documents

    @staticmethod
    def _digest_file(path: Path) -> bytes:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.digest()


def get_cached_rag() -> Im2RecipeRAG | None:
    """Return a cached RAG instance when enabled in settings."""

    global _RAG_CACHE
    settings = get_settings()
    if not settings.rag_enabled:
        return None
    if _RAG_CACHE is not None:
        return _RAG_CACHE

    model_path = settings.rag_model_path
    ensure_im2recipe_model(model_path)
    if not settings.rag_corpus_path.exists():
        raise FileNotFoundError(
            f"Recipe corpus not found at {settings.rag_corpus_path}. "
            "Provide a JSON corpus or disable REMY_RAG_ENABLED."
        )
    _RAG_CACHE = Im2RecipeRAG(
        model_path=model_path,
        corpus_path=settings.rag_corpus_path,
        embedding_dim=settings.rag_embedding_dim,
        index_path=settings.rag_index_path,
        index_trees=settings.rag_index_trees,
    )
    return _RAG_CACHE
