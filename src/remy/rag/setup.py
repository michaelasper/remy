"""CLI helper to download and prepare the im2recipe model."""

from __future__ import annotations

from pathlib import Path

from remy.config import get_settings
from remy.rag.im2recipe import IM2RECIPE_URL, ensure_im2recipe_model


def main() -> None:
    settings = get_settings()
    model_path: Path = settings.rag_model_path
    print(f"Downloading im2recipe model to {model_path} (source: {IM2RECIPE_URL})...")
    ensure_im2recipe_model(model_path)
    print("Download complete.")


if __name__ == "__main__":
    main()
