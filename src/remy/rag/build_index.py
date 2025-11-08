"""CLI helper to rebuild the Annoy recipe index."""

from __future__ import annotations

from remy.config import get_settings
from remy.rag.im2recipe import Im2RecipeRAG, ensure_im2recipe_model


def main() -> None:
    settings = get_settings()
    ensure_im2recipe_model(settings.rag_model_path)
    rag = Im2RecipeRAG(
        model_path=settings.rag_model_path,
        corpus_path=settings.rag_corpus_path,
        embedding_dim=settings.rag_embedding_dim,
        index_path=settings.rag_index_path,
        index_trees=settings.rag_index_trees,
    )
    print(
        f"Indexed {len(rag.documents)} recipes "
        f"into {settings.rag_index_path} (trees={settings.rag_index_trees})."
    )


if __name__ == "__main__":
    main()
