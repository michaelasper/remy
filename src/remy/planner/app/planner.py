"""Planner implementation entry point."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from textwrap import shorten
from typing import Iterable, List, Mapping, Optional

import httpx
from pydantic import ValidationError

from remy.config import get_settings
from remy.models.context import InventoryItem, PlanningContext
from remy.models.plan import (
    IngredientRequirement,
    InventoryDelta,
    Plan,
    PlanCandidate,
    ShoppingShortfall,
)
from remy.rag.im2recipe import get_cached_rag
from remy.search import search_recipes

from .constraint_engine import (
    AllergenExclusionRule,
    AttendeeScalingRule,
    BestBeforePriorityRule,
    ConstraintEngine,
    DietCompatibilityRule,
    InventoryCoverageRule,
    LeftoverUtilizationRule,
    MaxTimeRule,
    RecencyPenaltyRule,
)
from .utils import build_inventory_index, normalize_name, resolve_inventory_item

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a household dinner planner focused on composing cohesive, restaurant-quality dinners. "
    "Optimize for (1) well-rounded mains plus complementary sides, (2) culinary variety and seasonal balance, "
    "(3) low weekday prep time, and (4) household preferences. "
    "Use pantry inventory when it makes sense, but do not hesitate to introduce extra ingredients—"
    "mark them as shopping_shortfall entries instead of avoiding good ideas. "
    "Return ONLY valid JSON matching this schema and ALWAYS provide 2-3 candidates:\n"
    '{\n'
    '  "date": "YYYY-MM-DD",\n'
    '  "candidates": [\n'
    '    {\n'
    '      "title": "string",\n'
    '      "estimated_time_min": number,\n'
    '      "servings": number,\n'
    '      "steps": ["short imperative sentence", ...],\n'
    '      "ingredients_required": [\n'
    '        {"ingredient_id": number|null, "name": "string", "qty_g": number, "qty_ml": number|null, "qty_count": number|null}\n'
    '      ],\n'
    '      "inventory_deltas": [\n'
    '        {"ingredient_id": number, "use_g": number|null, "use_ml": number|null, "use_count": number|null}\n'
    '      ],\n'
    '      "shopping_shortfall": [\n'
    '        {"ingredient_id": number|null, "name": "string", "need_g": number|null, "need_ml": number|null, "need_count": number|null, "reason": "not_in_inventory|insufficient_stock"}\n'
    '      ],\n'
    '      "macros_per_serving": {"kcal": number|null, "protein_g": number|null, "carb_g": number|null, "fat_g": number|null}|null\n'
    '    }\n'
    '  ]\n'
    '}\n'
    "Rules: candidates array MUST contain 2 or 3 entries, steps must be an array (no combined paragraphs), "
    "include inventory_deltas for every ingredient that exists in inventory, and list shopping_shortfall rows for "
    "any ingredient that is missing OR insufficient so new groceries can be purchased. "
    "Draw inspiration from any recipe snippets provided and make each candidate feel complete (protein + sides or garnishes). "
    "Do not emit prose, Markdown, or keys outside this schema. "
    "Example output:\n"
    '{\n'
    '  "date": "2025-01-01",\n'
    '  "candidates": [\n'
    '    {\n'
    '      "title": "Tofu Stir-Fry",\n'
    '      "estimated_time_min": 25,\n'
    '      "servings": 2,\n'
    '      "steps": ["press tofu", "sear tofu", "stir-fry vegetables", "combine and serve"],\n'
    '      "ingredients_required": [\n'
    '        {"ingredient_id": 1, "name": "tofu", "qty_g": 350, "qty_ml": null, "qty_count": null}\n'
    '      ],\n'
    '      "inventory_deltas": [\n'
    '        {"ingredient_id": 1, "use_g": 350, "use_ml": null, "use_count": null}\n'
    '      ],\n'
    '      "shopping_shortfall": [],\n'
    '      "macros_per_serving": {"kcal": 420, "protein_g": 30, "carb_g": 18, "fat_g": 20}\n'
    '    },\n'
    '    {\n'
    '      "title": "Chickpea Coconut Curry",\n'
    '      "estimated_time_min": 30,\n'
    '      "servings": 2,\n'
    '      "steps": ["sauté aromatics", "simmer chickpeas with coconut milk", "finish with spinach"],\n'
    '      "ingredients_required": [\n'
    '        {"ingredient_id": null, "name": "canned chickpeas", "qty_g": 400, "qty_ml": null, "qty_count": null},\n'
    '        {"ingredient_id": null, "name": "coconut milk", "qty_g": 350, "qty_ml": null, "qty_count": null},\n'
    '        {"ingredient_id": null, "name": "spinach", "qty_g": 150, "qty_ml": null, "qty_count": null}\n'
    '      ],\n'
    '      "inventory_deltas": [],\n'
    '      "shopping_shortfall": [\n'
    '        {"ingredient_id": null, "name": "canned chickpeas", "need_g": 400, "need_ml": null, "need_count": null, "reason": "not_in_inventory"}\n'
    '      ],\n'
    '      "macros_per_serving": {"kcal": 480, "protein_g": 20, "carb_g": 30, "fat_g": 25}\n'
    '    }\n'
    '  ]\n'
    '}\n'
)

USER_PROMPT_TEMPLATE = (
    "IMPORTANT CONSTRAINTS:\n"
    "- Diet: {diet}\n"
    "- Allergens to avoid: {allergens}\n"
    "- Max prep time: {max_time} minutes\n"
    "- Attendees: {attendees}\n"
    "You MUST honor the diet/allergen constraints and keep prep time within the limit.\n"
    "- Favor balanced, composed dinners (entrées with sides or toppings).\n"
    "- If pantry items are insufficient, still pitch the dish and capture the gap in shopping_shortfall.\n"
    "- When recipe inspiration snippets are present, weave those ideas or techniques into at least one candidate.\n"
    "Here is the planning context for {date}:\n{context_json}\n"
    "Return 2-3 dinner candidates that obey the schema. "
    "Respect diet/allergen constraints strictly, use near-expiry ingredients when practical, "
    "and make confident suggestions even if some items require shopping. "
    "If the context is incomplete, reply with {{\"date\": \"{date}\", \"candidates\": []}}."
    "{recipe_snippets}"
)

LLM_REQUEST_TIMEOUT = 30.0
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_search_terms(context: PlanningContext, limit: int = 5) -> list[str]:
    terms: list[str] = []
    inventory = sorted(
        context.inventory,
        key=lambda item: (item.best_before or context.date, item.name.lower()),
    )
    for item in inventory:
        name = (item.name or "").strip()
        if not name:
            continue
        terms.append(name)
        if len(terms) >= limit:
            break
    if not terms and context.leftovers:
        for leftover in context.leftovers:
            name = (leftover.name or "").strip()
            if name:
                terms.append(name)
                if len(terms) >= limit:
                    break
    return terms


def _collect_recipe_snippets(context: PlanningContext) -> str:
    sections: list[str] = []
    web_snippets = _collect_web_recipe_snippets(context)
    if web_snippets:
        sections.append(
            "Web inspiration:\n" + "\n".join(web_snippets)
        )
    rag_snippets = _collect_rag_snippet_lines(context)
    if rag_snippets:
        sections.append(
            "Im2Recipe retrievals:\n" + "\n".join(rag_snippets)
        )
    return "\n\n".join(sections)


def _collect_web_recipe_snippets(context: PlanningContext) -> list[str]:
    settings = get_settings()
    if not settings.planner_enable_recipe_search:
        return []

    terms = _extract_search_terms(context, limit=5)
    if not terms:
        return []

    query_parts = terms + [context.prefs.diet or "dinner", "recipe"]
    query = " ".join(query_parts)
    try:
        results = search_recipes(query, limit=settings.planner_recipe_search_results)
    except Exception as exc:  # pragma: no cover - best effort network call
        logger.warning("Recipe search failed: %s", exc)
        return []

    lines = []
    for idx, result in enumerate(results, start=1):
        snippet = shorten(result.snippet or "", width=220, placeholder="…")
        lines.append(f"{idx}. {result.title} — {snippet} (source: {result.link})")
    return lines


def _collect_rag_snippet_lines(context: PlanningContext) -> list[str]:
    rag = get_cached_rag()
    if rag is None:
        return []
    settings = get_settings()
    top_k = max(1, settings.rag_top_k)
    try:
        documents = rag.retrieve(context, top_k=top_k)
    except Exception as exc:  # pragma: no cover - retrieval best effort
        logger.warning("Im2Recipe RAG retrieval failed: %s", exc)
        return []
    snippets = []
    for idx, doc in enumerate(documents, start=1):
        snippets.append(f"{idx}. {rag.format_document(doc)}")
    return snippets


def _render_user_prompt(
    context: PlanningContext,
    *,
    context_json: str,
    recipe_snippets: str,
) -> str:
    diet = context.prefs.diet or "omnivore"
    allergens_list = context.prefs.allergens or []
    allergens = ", ".join(allergens_list) if allergens_list else "none"
    max_time = context.prefs.max_time_min or 45
    attendees = context.constraints.attendees or 2
    snippet_block = (
        "\nHere are recent recipe ideas from the web (use for inspiration, do not copy verbatim):\n"
        f"{recipe_snippets}"
        if recipe_snippets
        else ""
    )
    return USER_PROMPT_TEMPLATE.format(
        date=str(context.date),
        context_json=context_json,
        diet=diet,
        allergens=allergens,
        max_time=max_time,
        attendees=attendees,
        recipe_snippets=snippet_block,
    )


@dataclass(frozen=True)
class RecipeIngredient:
    name: str
    quantity_g: float
    optional: bool = False


@dataclass(frozen=True)
class Recipe:
    title: str
    ingredients: List[RecipeIngredient]
    tags: Iterable[str]
    steps: List[str]
    estimated_time_min: int
    primary_ingredients: Iterable[str]
    servings: int = 4


RECIPES: List[Recipe] = [
    Recipe(
        title="Lemon Herb Chicken with Roasted Vegetables",
        ingredients=[
            RecipeIngredient("chicken thigh, boneless", 450),
            RecipeIngredient("lemon", 80, optional=True),
            RecipeIngredient("broccoli", 300),
            RecipeIngredient("olive oil", 30),
            RecipeIngredient("garlic", 12),
        ],
        tags={"omnivore", "gluten-free"},
        steps=[
            "Marinate chicken with lemon juice, garlic, and herbs.",
            "Roast vegetables tossed in olive oil.",
            "Sear chicken and serve over roasted vegetables.",
        ],
        estimated_time_min=40,
        primary_ingredients=["chicken", "broccoli"],
    ),
    Recipe(
        title="Chickpea Coconut Curry",
        ingredients=[
            RecipeIngredient("canned chickpeas", 400),
            RecipeIngredient("coconut milk", 350),
            RecipeIngredient("spinach", 150),
            RecipeIngredient("onion", 120),
            RecipeIngredient("garlic", 10),
        ],
        tags={"vegan", "vegetarian", "gluten-free"},
        steps=[
            "Sauté aromatics until fragrant.",
            "Simmer chickpeas with coconut milk and spices.",
            "Stir in spinach to wilt before serving with rice.",
        ],
        estimated_time_min=30,
        primary_ingredients=["canned chickpeas"],
    ),
    Recipe(
        title="Seared Salmon with Citrus Salad",
        ingredients=[
            RecipeIngredient("salmon fillet", 500),
            RecipeIngredient("mixed greens", 150),
            RecipeIngredient("orange", 160),
            RecipeIngredient("olive oil", 20),
            RecipeIngredient("almonds", 40, optional=True),
        ],
        tags={"pescatarian", "low-carb"},
        steps=[
            "Pan-sear salmon until crisp and cooked through.",
            "Assemble salad with citrus segments and toasted almonds.",
            "Serve salmon over salad with vinaigrette.",
        ],
        estimated_time_min=25,
        primary_ingredients=["salmon", "greens"],
    ),
    Recipe(
        title="Vegetable Stir-Fry with Tofu",
        ingredients=[
            RecipeIngredient("tofu", 400),
            RecipeIngredient("bell pepper", 150),
            RecipeIngredient("carrot", 120),
            RecipeIngredient("soy sauce", 40),
            RecipeIngredient("garlic", 10),
        ],
        tags={"vegan", "vegetarian"},
        steps=[
            "Press and cube tofu, then sear until golden.",
            "Stir-fry vegetables until crisp-tender.",
            "Combine with sauce and simmer briefly before serving over rice or noodles.",
        ],
        estimated_time_min=20,
        primary_ingredients=["tofu"],
    ),
    Recipe(
        title="Hearty Lentil Soup",
        ingredients=[
            RecipeIngredient("dry lentils", 300),
            RecipeIngredient("celery", 80),
            RecipeIngredient("carrot", 120),
            RecipeIngredient("onion", 120),
            RecipeIngredient("vegetable broth", 600),
        ],
        tags={"vegan", "vegetarian", "gluten-free"},
        steps=[
            "Sauté mirepoix until softened.",
            "Add lentils and broth, then simmer until tender.",
            "Season to taste and finish with fresh herbs.",
        ],
        estimated_time_min=45,
        primary_ingredients=["lentils"],
    ),
]


def _build_constraint_engine() -> ConstraintEngine:
    """Create a constraint engine instance with the default rule set."""
    return ConstraintEngine(
        hard_rules=[
            DietCompatibilityRule(),
            AllergenExclusionRule(),
            MaxTimeRule(),
        ],
        soft_rules=[
            InventoryCoverageRule(),
            BestBeforePriorityRule(),
            LeftoverUtilizationRule(),
            RecencyPenaltyRule(),
            AttendeeScalingRule(),
        ],
    )


def _build_candidate(
    recipe: Recipe,
    context: PlanningContext,
    inventory_lookup: Mapping[str, InventoryItem],
) -> PlanCandidate:
    servings = context.constraints.attendees or recipe.servings
    requirements: List[IngredientRequirement] = []
    deltas: List[InventoryDelta] = []
    shortfalls: List[ShoppingShortfall] = []

    for ingredient in recipe.ingredients:
        normalized = normalize_name(ingredient.name)
        matched_item: Optional[InventoryItem] = resolve_inventory_item(normalized, inventory_lookup)
        quantity_needed = ingredient.quantity_g

        if matched_item is not None:
            available = matched_item.quantity or 0.0
            use_amount = min(available, quantity_needed)
            requirements.append(
                IngredientRequirement(
                    ingredient_id=matched_item.id,
                    name=matched_item.name,
                    quantity_g=quantity_needed,
                )
            )
            if use_amount > 0:
                deltas.append(
                    InventoryDelta(
                        ingredient_id=matched_item.id,
                        use_g=use_amount,
                    )
                )
            shortfall_amount = max(quantity_needed - available, 0.0)
            if shortfall_amount > 0.01:
                shortfalls.append(
                    ShoppingShortfall(
                        ingredient_id=matched_item.id,
                        name=matched_item.name,
                        need_g=round(shortfall_amount, 2),
                        reason="insufficient_stock",
                    )
                )
        else:
            requirements.append(
                IngredientRequirement(
                    ingredient_id=None,
                    name=ingredient.name,
                    quantity_g=quantity_needed,
                )
            )
            if not ingredient.optional:
                shortfalls.append(
                    ShoppingShortfall(
                        ingredient_id=None,
                        name=ingredient.name,
                        need_g=quantity_needed,
                        reason="not_in_inventory",
                    )
                )

    return PlanCandidate(
        title=recipe.title,
        estimated_time_min=recipe.estimated_time_min,
        servings=servings,
        steps=list(recipe.steps),
        ingredients_required=requirements,
        inventory_deltas=deltas,
        shopping_shortfall=shortfalls,
        macros_per_serving=None,
    )


def _fallback_candidate(context: PlanningContext) -> PlanCandidate:
    name = "Pantry Pasta"
    steps = [
        "Boil pasta until al dente.",
        "Sauté garlic in olive oil, add canned tomatoes.",
        "Combine pasta with sauce and serve with herbs.",
    ]
    return PlanCandidate(
        title=name,
        estimated_time_min=context.prefs.max_time_min or 25,
        servings=context.constraints.attendees or 2,
        steps=steps,
        ingredients_required=[
            IngredientRequirement(ingredient_id=None, name="pasta", quantity_g=300),
            IngredientRequirement(ingredient_id=None, name="canned tomatoes", quantity_g=400),
        ],
        inventory_deltas=[],
        shopping_shortfall=[
            ShoppingShortfall(name="pasta", need_g=300, reason="not_in_inventory"),
            ShoppingShortfall(name="canned tomatoes", need_g=400, reason="not_in_inventory"),
        ],
        macros_per_serving=None,
    )


def _generate_rule_based_plan(context: PlanningContext) -> Plan:
    """Generate dinner plan candidates using the declarative constraint engine."""
    inventory_lookup = build_inventory_index(context.inventory)
    engine = _build_constraint_engine()
    evaluations = engine.rank_recipes(context, RECIPES)

    candidates: List[PlanCandidate] = [
        _build_candidate(evaluation.recipe, context, inventory_lookup)
        for evaluation in evaluations[:3]
    ]

    if not candidates:
        if context.inventory:
            candidates.append(_build_candidate(RECIPES[0], context, inventory_lookup))
        else:
            candidates.append(_fallback_candidate(context))

    return Plan(date=context.date, candidates=candidates)


def generate_plan(context: PlanningContext) -> Plan:
    """Generate dinner plan candidates, preferring the configured LLM when available."""

    llm_plan = _generate_plan_with_llm(context)
    if llm_plan is not None:
        return llm_plan
    return _generate_rule_based_plan(context)


def _generate_plan_with_llm(context: PlanningContext) -> Optional[Plan]:
    """Call the configured LLM endpoint and parse the response into a Plan."""

    settings = get_settings()
    base_url = settings.planner_llm_base_url
    if not base_url:
        return None

    provider = (settings.planner_llm_provider or "openai").strip().lower()
    try:
        if provider == "ollama":
            return _request_ollama_plan(
                context=context,
                base_url=base_url,
                model=settings.planner_llm_model,
                temperature=settings.planner_llm_temperature,
                max_tokens=settings.planner_llm_max_tokens,
            )
        return _request_openai_plan(
            context=context,
            base_url=base_url,
            model=settings.planner_llm_model,
            temperature=settings.planner_llm_temperature,
            max_tokens=settings.planner_llm_max_tokens,
        )
    except Exception as exc:
        logger.warning("Planner LLM request failed; using rule-based fallback: %s", exc)
        return None


def _request_openai_plan(
    *,
    context: PlanningContext,
    base_url: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> Plan:
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"

    context_json = context.model_dump_json()
    recipe_snippets = _collect_recipe_snippets(context)
    user_prompt = _render_user_prompt(
        context,
        context_json=context_json,
        recipe_snippets=recipe_snippets,
    )
    safe_temperature = max(0.0, float(temperature))
    safe_max_tokens = max(1, int(max_tokens))
    payload = {
        "model": model,
        "temperature": safe_temperature,
        "max_tokens": safe_max_tokens,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }

    with httpx.Client(timeout=LLM_REQUEST_TIMEOUT) as client:
        response = client.post(endpoint, json=payload)
    response.raise_for_status()

    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        raise ValueError("Planner LLM returned no choices.")
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        raise ValueError("Planner LLM returned an empty response.")

    plan_payload = _extract_json_blob(content)
    try:
        return Plan.model_validate_json(plan_payload)
    except ValidationError as exc:
        snippet = plan_payload.strip().replace("\n", " ")[:200]
        raise ValueError(f"Planner LLM output failed validation: {exc}; payload={snippet}") from exc


def _extract_json_blob(text: str) -> str:
    """Return a JSON object substring from raw LLM text."""

    match = _JSON_BLOCK_RE.search(text)
    if match:
        return match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1].strip()

    return text.strip()


def _request_ollama_plan(
    *,
    context: PlanningContext,
    base_url: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> Plan:
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/api/chat"):
        endpoint = f"{endpoint}/api/chat"

    context_json = context.model_dump_json()
    recipe_snippets = _collect_recipe_snippets(context)
    user_prompt = _render_user_prompt(
        context,
        context_json=context_json,
        recipe_snippets=recipe_snippets,
    )
    safe_temperature = max(0.0, float(temperature))
    safe_max_tokens = max(1, int(max_tokens))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "temperature": safe_temperature,
            "num_predict": safe_max_tokens,
        },
    }

    with httpx.Client(timeout=LLM_REQUEST_TIMEOUT) as client:
        response = client.post(endpoint, json=payload)
    response.raise_for_status()

    body = response.json()
    message = body.get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        raise ValueError("Ollama response did not include content.")

    plan_payload = _extract_json_blob(content)
    try:
        return Plan.model_validate_json(plan_payload)
    except ValidationError as exc:
        snippet = plan_payload.strip().replace("\n", " ")[:200]
        raise ValueError(f"Ollama planner output failed validation: {exc}; payload={snippet}") from exc
