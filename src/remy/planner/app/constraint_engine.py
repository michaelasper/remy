"""Constraint-based rule engine backing the meal planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, TYPE_CHECKING

from remy.models.context import InventoryItem, LeftoverItem, PlanningContext

from .utils import (
    build_inventory_index,
    build_leftover_index,
    normalize_name,
    resolve_inventory_item,
    resolve_leftover_item,
)

if TYPE_CHECKING:  # pragma: no cover - type-only imports
    from .planner import Recipe
    from .planner import RecipeIngredient


@dataclass(frozen=True)
class RuleResult:
    """Outcome of applying an individual rule to a recipe."""

    name: str
    passed: bool
    score_adjustment: float = 0.0
    details: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ConstraintEvaluation:
    """Aggregate rule evaluation for a single recipe."""

    recipe: "Recipe"
    score: float
    rule_results: Tuple[RuleResult, ...]


@dataclass(frozen=True)
class PlanningSnapshot:
    """Lightweight snapshot shared across rule evaluations."""

    context: PlanningContext
    inventory_index: Dict[str, InventoryItem]
    leftovers_index: Dict[str, LeftoverItem]
    current_date: date


class ConstraintRule:
    """Base class contract for all planning rules."""

    name: str
    hard: bool

    def evaluate(self, recipe: "Recipe", snapshot: PlanningSnapshot) -> RuleResult:
        raise NotImplementedError


class DietCompatibilityRule(ConstraintRule):
    name = "diet_compatibility"
    hard = True

    def evaluate(self, recipe: "Recipe", snapshot: PlanningSnapshot) -> RuleResult:
        diet = (snapshot.context.prefs.diet or "").strip().lower()
        if not diet:
            return RuleResult(self.name, True)
        recipe_tags = {normalize_name(tag) for tag in recipe.tags}
        if diet in recipe_tags or "flex" in recipe_tags:
            return RuleResult(self.name, True, 0.5)
        return RuleResult(
            self.name,
            False,
            details=(f"recipe missing tag for diet '{diet}'",),
        )


class AllergenExclusionRule(ConstraintRule):
    name = "allergen_exclusion"
    hard = True

    def evaluate(self, recipe: "Recipe", snapshot: PlanningSnapshot) -> RuleResult:
        allergens = {normalize_name(allergen) for allergen in snapshot.context.prefs.allergens}
        if not allergens:
            return RuleResult(self.name, True)

        for ingredient in recipe.ingredients:
            ingredient_name = normalize_name(ingredient.name)
            if any(allergen in ingredient_name for allergen in allergens):
                return RuleResult(
                    self.name,
                    False,
                    details=(f"ingredient '{ingredient.name}' violates allergen policy",),
                )

        return RuleResult(self.name, True, 0.3)


class MaxTimeRule(ConstraintRule):
    name = "time_limit"
    hard = True

    def evaluate(self, recipe: "Recipe", snapshot: PlanningSnapshot) -> RuleResult:
        max_time = snapshot.context.prefs.max_time_min
        if max_time is None:
            return RuleResult(self.name, True)
        if recipe.estimated_time_min <= max_time:
            return RuleResult(self.name, True, 0.2)
        return RuleResult(
            self.name,
            False,
            details=(
                f"recipe requires {recipe.estimated_time_min} min, "
                f"exceeding limit of {max_time} min",
            ),
        )


class InventoryCoverageRule(ConstraintRule):
    name = "inventory_coverage"
    hard = False

    def evaluate(self, recipe: "Recipe", snapshot: PlanningSnapshot) -> RuleResult:
        if not recipe.ingredients:
            return RuleResult(self.name, True)

        coverage_scores: List[float] = []
        missing: List[str] = []
        primary_hits = 0
        primary_set = {normalize_name(name) for name in getattr(recipe, "primary_ingredients", [])}

        for ingredient in recipe.ingredients:
            normalized = normalize_name(ingredient.name)
            match = resolve_inventory_item(normalized, snapshot.inventory_index)
            if match is None:
                missing.append(ingredient.name)
                continue

            needed = getattr(ingredient, "quantity_g", None) or 0.0
            available = match.quantity or 0.0
            if needed <= 0:
                coverage_scores.append(1.0)
                continue
            coverage_ratio = min(available / needed, 1.0) if available > 0 else 0.0
            coverage_scores.append(coverage_ratio)
            if primary_set and normalized in primary_set:
                primary_hits += 1

        if not coverage_scores and missing:
            return RuleResult(
                self.name,
                True,
                score_adjustment=-1.0,
                details=(f"no inventory coverage for {', '.join(missing)}",),
            )

        average_coverage = sum(coverage_scores) / len(coverage_scores) if coverage_scores else 0.0
        score = 1.5 * average_coverage - 0.4 * len(missing) + 0.6 * primary_hits
        detail_messages = []
        if missing:
            detail_messages.append(f"missing {', '.join(missing)}")
        if primary_hits:
            detail_messages.append(f"covers {primary_hits} primary ingredients")
        return RuleResult(
            self.name,
            True,
            score_adjustment=score,
            details=tuple(detail_messages),
        )


class BestBeforePriorityRule(ConstraintRule):
    name = "expiry_priority"
    hard = False

    def evaluate(self, recipe: "Recipe", snapshot: PlanningSnapshot) -> RuleResult:
        total_bonus = 0.0
        details: List[str] = []
        for ingredient in recipe.ingredients:
            normalized = normalize_name(ingredient.name)
            match = resolve_inventory_item(normalized, snapshot.inventory_index)
            if match is None or match.best_before is None:
                continue
            days_remaining = (match.best_before - snapshot.current_date).days
            if days_remaining < 0:
                total_bonus += 1.5
                details.append(f"{match.name} expired")
            elif days_remaining <= 2:
                total_bonus += 1.2
                details.append(f"{match.name} expiring in {days_remaining}d")
            elif days_remaining <= 7:
                total_bonus += 0.6
            elif days_remaining <= 14:
                total_bonus += 0.2

        return RuleResult(self.name, True, score_adjustment=total_bonus, details=tuple(details))


class LeftoverUtilizationRule(ConstraintRule):
    name = "leftover_utilization"
    hard = False

    def evaluate(self, recipe: "Recipe", snapshot: PlanningSnapshot) -> RuleResult:
        if not snapshot.context.leftovers:
            return RuleResult(self.name, True)

        bonus = 0.0
        used_leftovers: List[str] = []
        for ingredient in recipe.ingredients:
            normalized = normalize_name(ingredient.name)
            leftover = resolve_leftover_item(normalized, snapshot.leftovers_index)
            if leftover is None:
                continue
            bonus += 0.8
            used_leftovers.append(leftover.name)

        if not used_leftovers:
            return RuleResult(self.name, True, score_adjustment=-0.1)

        return RuleResult(
            self.name,
            True,
            score_adjustment=bonus,
            details=(f"uses leftovers: {', '.join(sorted(set(used_leftovers)))}",),
        )


class RecencyPenaltyRule(ConstraintRule):
    name = "recency_penalty"
    hard = False

    def evaluate(self, recipe: "Recipe", snapshot: PlanningSnapshot) -> RuleResult:
        if not snapshot.context.recent_meals:
            return RuleResult(self.name, True)

        recent_titles = {
            normalize_name(meal.title): meal
            for meal in snapshot.context.recent_meals
        }
        recipe_name = normalize_name(recipe.title)
        if recipe_name not in recent_titles:
            return RuleResult(self.name, True, score_adjustment=0.3)

        meal = recent_titles[recipe_name]
        days_since = (snapshot.current_date - meal.date).days
        penalty = max(1.5 - 0.2 * max(days_since, 0), 0.3)

        details = (
            f"served {days_since}d ago, applying penalty {penalty:.2f}",
        )
        return RuleResult(
            self.name,
            True,
            score_adjustment=-penalty,
            details=details,
        )


class AttendeeScalingRule(ConstraintRule):
    """Soft rule rewarding recipes that scale cleanly to attendee counts."""

    name = "attendee_scaling"
    hard = False

    def evaluate(self, recipe: "Recipe", snapshot: PlanningSnapshot) -> RuleResult:
        attendees = snapshot.context.constraints.attendees
        if not attendees or recipe.servings <= 0:
            return RuleResult(self.name, True)

        ratio = attendees / recipe.servings
        if 0.5 <= ratio <= 2.0:
            score = 0.4
        else:
            score = -0.2

        details: Tuple[str, ...] = ()
        if score < 0:
            details = (f"servings ratio {ratio:.2f} less ideal for {attendees} diners",)
        return RuleResult(self.name, True, score_adjustment=score, details=details)


class ConstraintEngine:
    """Evaluate candidate recipes against declarative rules."""

    def __init__(
        self,
        hard_rules: Sequence[ConstraintRule],
        soft_rules: Sequence[ConstraintRule],
    ) -> None:
        self._hard_rules = tuple(hard_rules)
        self._soft_rules = tuple(soft_rules)

    def evaluate_recipe(self, recipe: "Recipe", snapshot: PlanningSnapshot) -> Optional[ConstraintEvaluation]:
        """Evaluate a recipe, returning a scored evaluation if constraints pass."""
        results: List[RuleResult] = []

        for rule in self._hard_rules:
            result = rule.evaluate(recipe, snapshot)
            results.append(result)
            if not result.passed:
                return None

        score = 0.0
        for rule in self._soft_rules:
            result = rule.evaluate(recipe, snapshot)
            results.append(result)
            score += result.score_adjustment

        return ConstraintEvaluation(recipe=recipe, score=score, rule_results=tuple(results))

    def rank_recipes(
        self,
        context: PlanningContext,
        recipes: Iterable["Recipe"],
    ) -> List[ConstraintEvaluation]:
        """Return sorted evaluations for recipes that satisfy hard constraints."""
        snapshot = PlanningSnapshot(
            context=context,
            inventory_index=build_inventory_index(context.inventory),
            leftovers_index=build_leftover_index(context.leftovers),
            current_date=context.date,
        )

        evaluations: List[ConstraintEvaluation] = []
        for recipe in recipes:
            evaluation = self.evaluate_recipe(recipe, snapshot)
            if evaluation is not None:
                evaluations.append(evaluation)

        evaluations.sort(key=lambda evaluation: evaluation.score, reverse=True)
        return evaluations
