"""Planner implementation entry point."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Optional

from remy.models.context import InventoryItem, PlanningContext
from remy.models.plan import (
    IngredientRequirement,
    InventoryDelta,
    Plan,
    PlanCandidate,
    ShoppingShortfall,
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


def _normalize_name(value: str) -> str:
    return " ".join(value.lower().split())


def _inventory_map(inventory: List[InventoryItem]) -> Dict[str, InventoryItem]:
    return {_normalize_name(item.name): item for item in inventory}


def _best_before_score(item: InventoryItem, current_date: date) -> float:
    if item.best_before is None:
        return 0.0
    days_remaining = (item.best_before - current_date).days
    if days_remaining < 0:
        return 2.0
    if days_remaining <= 2:
        return 1.5
    if days_remaining <= 7:
        return 1.0
    if days_remaining <= 14:
        return 0.5
    return 0.0


def _diet_allows(recipe: Recipe, context: PlanningContext) -> bool:
    diet = (context.prefs.diet or "").strip().lower()
    if not diet:
        return True
    return diet in {tag.lower() for tag in recipe.tags} or "flex" in {
        tag.lower() for tag in recipe.tags
    }


def _contains_allergen(recipe: Recipe, allergens: Iterable[str]) -> bool:
    normalized_allergens = {_normalize_name(allergen) for allergen in allergens}
    if not normalized_allergens:
        return False
    for ingredient in recipe.ingredients:
        ingredient_name = _normalize_name(ingredient.name)
        if any(allergen in ingredient_name for allergen in normalized_allergens):
            return True
    return False


def _score_recipe(
    recipe: Recipe,
    context: PlanningContext,
    inventory_lookup: Dict[str, InventoryItem],
) -> float:
    score = 0.0
    current_date = context.date or date.today()

    primary_matches = 0
    for primary in recipe.primary_ingredients:
        normalized = _normalize_name(primary)
        for key, item in inventory_lookup.items():
            if normalized in key:
                primary_matches += 1
                score += 1.5 + _best_before_score(item, current_date)
                break

    if primary_matches == 0:
        score -= 1.0

    if _diet_allows(recipe, context):
        score += 1.0
    else:
        score -= 2.0

    allergens = context.prefs.allergens if context.prefs else []
    if _contains_allergen(recipe, allergens):
        return -10.0

    max_time = context.prefs.max_time_min or 45
    if recipe.estimated_time_min <= max_time:
        score += 1.0
    else:
        score -= 0.5

    recent_titles = {
        _normalize_name(meal.title)
        for meal in context.recent_meals
        if getattr(meal, "title", None)
    }
    if _normalize_name(recipe.title) in recent_titles:
        score -= 1.0

    return score


def _build_candidate(
    recipe: Recipe,
    context: PlanningContext,
    inventory_lookup: Dict[str, InventoryItem],
) -> PlanCandidate:
    servings = context.constraints.attendees or recipe.servings
    requirements: List[IngredientRequirement] = []
    deltas: List[InventoryDelta] = []
    shortfalls: List[ShoppingShortfall] = []

    for ingredient in recipe.ingredients:
        normalized = _normalize_name(ingredient.name)
        matched_item: Optional[InventoryItem] = None
        for key, item in inventory_lookup.items():
            if normalized in key or key in normalized:
                matched_item = item
                break

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


def generate_plan(context: PlanningContext) -> Plan:
    """Generate dinner plan candidates using simple heuristic scoring."""

    inventory_lookup = _inventory_map(context.inventory)

    scored: List[tuple[float, Recipe]] = []
    for recipe in RECIPES:
        score = _score_recipe(recipe, context, inventory_lookup)
        scored.append((score, recipe))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    top_recipes = [recipe for score, recipe in scored if score > -5][:3]

    candidates: List[PlanCandidate] = []
    for recipe in top_recipes:
        candidates.append(_build_candidate(recipe, context, inventory_lookup))

    if not candidates:
        if context.inventory:
            candidates.append(_build_candidate(RECIPES[0], context, inventory_lookup))
        else:
            candidates.append(_fallback_candidate(context))

    return Plan(date=context.date, candidates=candidates)
