"""Recipe search helpers powered by DuckDuckGo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from duckduckgo_search import DDGS


@dataclass(frozen=True)
class RecipeSearchResult:
    title: str
    link: str
    snippet: str


def search_recipes(query: str, *, limit: int = 5, region: str = "us-en") -> List[RecipeSearchResult]:
    """Return recipe-related web snippets for the supplied query."""

    results: List[RecipeSearchResult] = []
    if not query.strip() or limit <= 0:
        return results

    with DDGS(timeout=8) as ddgs:
        for item in ddgs.text(query, region=region, safesearch="moderate", max_results=limit):
            if not item:
                continue
            title = (item.get("title") or "").strip()
            href = (item.get("href") or item.get("link") or "").strip()
            body = (item.get("body") or item.get("snippet") or "").strip()
            if not title or not href:
                continue
            results.append(RecipeSearchResult(title=title, link=href, snippet=body))
            if len(results) >= limit:
                break
    return results
