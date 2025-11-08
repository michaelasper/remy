"""Tests for Recipe1M conversion utilities."""

from __future__ import annotations

import json

from remy.rag.recipe1m import convert_recipe1m


def test_convert_recipe1m_handles_lists_and_jsonl(tmp_path):
    recipe_list = [
        {
            "title": "Sample Dish",
            "description": "Tasty",
            "ingredients": [{"text": "tomatoes"}, {"text": "basil"}],
            "instructions": [{"text": "Chop"}, {"text": "Serve"}],
        },
        {
            "title": "Second Dish",
            "ingredients": ["flour", "water"],
            "instructions": ["Mix", "Bake"],
        },
    ]
    list_path = tmp_path / "recipes.json"
    list_path.write_text(json.dumps(recipe_list), encoding="utf-8")

    output_path = tmp_path / "converted.json"
    count = convert_recipe1m(list_path, output_path)
    assert count == 2
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data[0]["title"] == "Sample Dish"
    assert "tomatoes" in data[0]["ingredients"][0].lower()

    # JSONL input
    jsonl_path = tmp_path / "recipes.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(obj) for obj in recipe_list),
        encoding="utf-8",
    )
    output_path_2 = tmp_path / "converted2.json"
    count2 = convert_recipe1m(jsonl_path, output_path_2, limit=1)
    assert count2 == 1
