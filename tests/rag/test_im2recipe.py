"""Tests for the im2recipe retrieval helper."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from remy.models.context import Constraints, InventoryItem, PlanningContext, Preferences
from remy.rag.im2recipe import Im2RecipeRAG, ensure_im2recipe_model


def _write_dummy_model(path: Path) -> Path:
    path.write_bytes(b"remy-test-model")
    return path


def _write_corpus(path: Path) -> Path:
    payload = [
        {
            "title": "Roasted Tomato Pasta",
            "summary": "Slow-roasted tomatoes tossed with garlic pasta.",
            "ingredients": ["tomatoes", "garlic", "basil"],
            "instructions": ["Roast tomatoes", "Toss with pasta"],
        },
        {
            "title": "Citrus Herb Salad",
            "summary": "Juicy oranges with fennel and mint.",
            "ingredients": ["orange", "fennel", "mint"],
            "instructions": ["Segment citrus", "Dress with olive oil"],
        },
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_rag_retrieves_documents(tmp_path):
    model_path = _write_dummy_model(tmp_path / "model.t7")
    corpus_path = _write_corpus(tmp_path / "corpus.json")
    index_path = tmp_path / "index.ann"

    rag = Im2RecipeRAG(
        model_path=model_path,
        corpus_path=corpus_path,
        embedding_dim=64,
        index_path=index_path,
        index_trees=5,
    )
    assert index_path.exists()

    context = PlanningContext(
        date=date.today(),
        prefs=Preferences(diet="vegetarian"),
        inventory=[
            InventoryItem(id=1, name="tomatoes", qty=5, unit="count"),
            InventoryItem(id=2, name="garlic clove", qty=3, unit="count"),
        ],
        leftovers=[],
        constraints=Constraints(attendees=2, time_window="dinner"),
    )

    results = rag.retrieve(context, top_k=1)
    assert len(results) == 1
    assert results[0].title
    snippet = rag.format_document(results[0])
    assert results[0].title in snippet

    rag_again = Im2RecipeRAG(
        model_path=model_path,
        corpus_path=corpus_path,
        embedding_dim=64,
        index_path=index_path,
        index_trees=5,
    )
    results_again = rag_again.retrieve(context, top_k=1)
    assert results_again[0].title == results[0].title


def test_ensure_model_download_works_with_local_source(tmp_path, monkeypatch):
    # create a gzipped dummy model
    target = tmp_path / "im2recipe_model.t7"
    gz_source = tmp_path / "model.t7.gz"
    raw_model = tmp_path / "raw_model.t7"
    raw_model.write_bytes(b"rag-model")

    import gzip

    with gzip.open(gz_source, "wb") as handle:
        handle.write(raw_model.read_bytes())

    ensure_im2recipe_model(target, source_url=gz_source.as_uri())
    assert target.exists()
    assert target.read_bytes() == raw_model.read_bytes()
