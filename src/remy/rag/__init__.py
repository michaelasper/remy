"""Recipe retrieval helpers backed by the im2recipe model."""

from remy.rag.build_index import main as build_index
from remy.rag.im2recipe import (
    IM2RECIPE_URL,
    Im2RecipeRAG,
    RecipeDocument,
    ensure_im2recipe_model,
    get_cached_rag,
)
from remy.rag.recipe1m import convert_recipe1m

__all__ = [
    "IM2RECIPE_URL",
    "Im2RecipeRAG",
    "RecipeDocument",
    "ensure_im2recipe_model",
    "get_cached_rag",
    "build_index",
    "convert_recipe1m",
]
