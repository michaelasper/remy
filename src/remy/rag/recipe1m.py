"""Utilities to convert Recipe1M-style exports into the Remy corpus format."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Iterable


def _open_maybe_gzip(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _normalize_ingredients(raw) -> list[str]:
    items: list[str] = []
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, str):
                text = entry.strip()
            elif isinstance(entry, dict):
                text = str(entry.get("text") or entry.get("ingredient") or "").strip()
            else:
                text = str(entry).strip()
            if text:
                items.append(text)
    elif isinstance(raw, str):
        items.append(raw.strip())
    return items


def _normalize_instructions(raw) -> list[str]:
    steps: list[str] = []
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, str):
                text = entry.strip()
            elif isinstance(entry, dict):
                text = str(entry.get("text") or "").strip()
            else:
                text = str(entry).strip()
            if text:
                steps.append(text)
    elif isinstance(raw, str):
        steps.append(raw.strip())
    return steps


def _iter_recipe1m_entries(path: Path) -> Iterable[dict]:
    with _open_maybe_gzip(path) as handle:
        first_char = handle.read(1)
        handle.seek(0)
        if first_char == "[":
            data = json.load(handle)
            for entry in data:
                yield entry
        else:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


def convert_recipe1m(input_path: Path, output_path: Path, limit: int | None = None) -> int:
    documents = []
    for idx, entry in enumerate(_iter_recipe1m_entries(input_path)):
        title = str(entry.get("title") or entry.get("id") or f"recipe-{idx}").strip()
        summary = str(entry.get("description") or entry.get("summary") or "").strip()
        ingredients = _normalize_ingredients(entry.get("ingredients"))
        instructions = _normalize_instructions(entry.get("instructions"))
        if not instructions:
            continue
        documents.append(
            {
                "title": title or f"Recipe {idx}",
                "summary": summary,
                "ingredients": ingredients,
                "instructions": instructions,
                "source": entry.get("url") or entry.get("id"),
            }
        )
        if limit and len(documents) >= limit:
            break
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(documents, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(documents)


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert Recipe1M exports into Remy corpus JSON.")
    parser.add_argument("--input", type=Path, required=True, help="Path to Recipe1M JSON or JSONL(.gz)")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/rag/recipes_recipe1m.json"),
        help="Destination corpus path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on number of recipes to extract.",
    )
    return parser


def main() -> None:
    parser = build_cli()
    args = parser.parse_args()
    count = convert_recipe1m(args.input, args.output, limit=args.limit)
    print(f"Wrote {count} recipes to {args.output}")


if __name__ == "__main__":
    main()
