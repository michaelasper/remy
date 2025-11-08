"""Diff and validation agent."""
# mypy: ignore-errors

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from remy.agents.base import Agent
from remy.models.context import InventoryItem, PlanningContext
from remy.models.plan import (
    IngredientRequirement,
    InventoryDelta,
    Macros,
    Plan,
    PlanCandidate,
    ShoppingShortfall,
)

logger = logging.getLogger(__name__)

_WEIGHT_UNITS = {
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "kg": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
    "mg": 0.001,
    "milligram": 0.001,
    "milligrams": 0.001,
    "lb": 453.592,
    "lbs": 453.592,
    "pound": 453.592,
    "pounds": 453.592,
    "oz": 28.3495,
    "ounce": 28.3495,
    "ounces": 28.3495,
}
_VOLUME_UNITS = {
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "cup": 240.0,
    "cups": 240.0,
    "tbsp": 15.0,
    "tablespoon": 15.0,
    "tablespoons": 15.0,
    "tbs": 15.0,
    "tsp": 5.0,
    "teaspoon": 5.0,
    "teaspoons": 5.0,
    "fl oz": 29.5735,
    "floz": 29.5735,
    "fluid ounce": 29.5735,
    "fluid ounces": 29.5735,
    "pint": 473.176,
    "pints": 473.176,
    "quart": 946.353,
    "quarts": 946.353,
    "gallon": 3785.41,
    "gallons": 3785.41,
}
_COUNT_UNITS = {"count", "ea", "each", "unit", "piece", "pieces", "pc", "pcs"}

_COUNT_TO_WEIGHT_G = 75.0  # heuristic grams per count when only counts provided
_MACRO_PROTEIN_SHARE = 0.25
_MACRO_FAT_SHARE = 0.08


@dataclass
class InventoryBuckets:
    weight_g: float = 0.0
    volume_ml: float = 0.0
    count: float = 0.0

    def clone(self) -> "InventoryBuckets":
        return InventoryBuckets(
            weight_g=self.weight_g,
            volume_ml=self.volume_ml,
            count=self.count,
        )


class DiffValidator(Agent[tuple[PlanningContext, Plan], Plan]):
    """
    Normalize planner output, compute shortages, and validate schema compliance.

    Ensures inventory deltas never exceed available stock and shortfalls are populated for
    ingredients that are missing or insufficient.
    """

    def run(self, payload: tuple[PlanningContext, Plan]) -> Plan:
        context, plan = payload
        inventory_state, unit_warnings = self._build_inventory_state(context.inventory)
        name_index = self._build_name_index(context.inventory)
        normalized_candidates: list[PlanCandidate] = []

        for candidate in plan.candidates:
            candidate_inventory = {
                item_id: buckets.clone() for item_id, buckets in inventory_state.items()
            }
            normalized_candidates.append(
                self._normalize_candidate(
                    candidate, candidate_inventory, name_index, unit_warnings
                )
            )

        return Plan(date=plan.date, candidates=normalized_candidates)

    def _build_inventory_state(
        self, inventory: list[InventoryItem]
    ) -> tuple[Dict[int, InventoryBuckets], Dict[int, str]]:
        state: Dict[int, InventoryBuckets] = {}
        warnings: Dict[int, str] = {}
        for item in inventory:
            if item.id is None:
                continue
            quantity = float(item.quantity or 0.0)
            unit = (item.unit or "").strip().lower()
            if quantity <= 0:
                continue
            unit_type, value, recognized = self._convert_unit(quantity, unit)
            if value is None:
                continue
            buckets = InventoryBuckets()
            if unit_type == "g":
                buckets.weight_g = value
            elif unit_type == "ml":
                buckets.volume_ml = value
            else:
                buckets.count = value
            state[item.id] = buckets
            if not recognized:
                warnings[item.id] = (
                    f"Inventory item '{item.name}' uses unit '{item.unit}', treated as count."
                )
        return state, warnings

    def _build_name_index(self, inventory: list[InventoryItem]) -> Dict[str, int]:
        index: Dict[str, int] = {}
        for item in inventory:
            if item.id is None:
                continue
            name = self._normalize_name(item.name)
            if name and name not in index:
                index[name] = item.id
        return index

    def _normalize_candidate(
        self,
        candidate: PlanCandidate,
        inventory_state: Dict[int, InventoryBuckets],
        name_index: Dict[str, int],
        unit_warnings: Dict[int, str],
    ) -> PlanCandidate:
        usage: Dict[int, Dict[str, float]] = {}
        shortfalls: list[ShoppingShortfall] = []
        diagnostics: list[str] = []
        diag_seen: Set[str] = set()

        for requirement in candidate.ingredients_required:
            req_amount, req_type = self._extract_requirement_amount(requirement)
            if req_amount is None or req_amount <= 0 or req_type is None:
                continue

            inventory_id = self._resolve_inventory_id(requirement, name_index)
            if inventory_id is not None and inventory_id in inventory_state:
                buckets = inventory_state[inventory_id]
                available = self._available_for_type(buckets, req_type)
                use_amount = min(req_amount, available)
                if use_amount > 0:
                    usage_entry = usage.setdefault(
                        inventory_id, {"use_g": 0.0, "use_ml": 0.0, "use_count": 0.0}
                    )
                    usage_entry[f"use_{req_type}"] += use_amount
                    self._decrement_bucket(buckets, req_type, use_amount)
                    if inventory_id in unit_warnings:
                        self._add_diag(
                            diagnostics, diag_seen, unit_warnings[inventory_id], candidate.title
                        )
                deficit = req_amount - use_amount
                if deficit > 1e-6:
                    logger.info(
                        (
                            "DiffValidator clamp ingredient_id=%s name=%s "
                            "requested=%.2f%s available=%.2f%s"
                        ),
                        inventory_id,
                        requirement.name,
                        req_amount,
                        req_type,
                        use_amount,
                        req_type,
                    )
                    shortfalls.append(
                        self._build_shortfall(
                            requirement,
                            req_type,
                            deficit,
                            reason="insufficient_stock",
                            ingredient_id=inventory_id,
                        )
                    )
                continue
            logger.info(
                "DiffValidator missing ingredient name=%s requested=%.2f%s",
                requirement.name,
                req_amount,
                req_type,
            )
            shortfalls.append(
                self._build_shortfall(
                    requirement,
                    req_type,
                    req_amount,
                    reason="not_in_inventory",
                    ingredient_id=inventory_id,
                )
            )

        delta_models = [
            InventoryDelta(
                ingredient_id=ingredient_id,
                use_g=self._maybe_value(amounts.get("use_g")),
                use_ml=self._maybe_value(amounts.get("use_ml")),
                use_count=self._maybe_value(amounts.get("use_count")),
            )
            for ingredient_id, amounts in usage.items()
        ]
        macros, macro_notes = self._recompute_macros(candidate)
        for note in macro_notes:
            self._add_diag(diagnostics, diag_seen, note, candidate.title)

        normalized_candidate = candidate.model_copy(
            update={
                "inventory_deltas": delta_models,
                "shopping_shortfall": shortfalls,
                "macros_per_serving": macros or candidate.macros_per_serving,
                "diagnostics": diagnostics,
            }
        )
        return normalized_candidate

    def _extract_requirement_amount(
        self, requirement: IngredientRequirement
    ) -> tuple[Optional[float], Optional[str]]:
        if requirement.quantity_g is not None:
            return float(requirement.quantity_g), "g"
        if requirement.quantity_ml is not None:
            return float(requirement.quantity_ml), "ml"
        if requirement.quantity_count is not None:
            return float(requirement.quantity_count), "count"
        return None, None

    def _resolve_inventory_id(
        self,
        requirement: IngredientRequirement,
        name_index: Dict[str, int],
    ) -> Optional[int]:
        if requirement.ingredient_id is not None:
            return requirement.ingredient_id
        normalized = self._normalize_name(requirement.name)
        if normalized in name_index:
            return name_index[normalized]
        return None

    def _build_shortfall(
        self,
        requirement: IngredientRequirement,
        req_type: str,
        amount: float,
        *,
        reason: str,
        ingredient_id: Optional[int],
    ) -> ShoppingShortfall:
        kwargs = {
            "ingredient_id": ingredient_id,
            "name": requirement.name,
            "need_g": None,
            "need_ml": None,
            "need_count": None,
            "reason": reason,
        }
        field = {"g": "need_g", "ml": "need_ml", "count": "need_count"}[req_type]
        kwargs[field] = amount
        return ShoppingShortfall(**kwargs)

    @staticmethod
    def _maybe_value(value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        return value if value > 1e-6 else None

    def _convert_unit(self, quantity: float, unit: str) -> tuple[str, Optional[float], bool]:
        if unit in _WEIGHT_UNITS:
            return "g", quantity * _WEIGHT_UNITS[unit], True
        if unit in _VOLUME_UNITS:
            return "ml", quantity * _VOLUME_UNITS[unit], True
        if unit in _COUNT_UNITS or not unit:
            return "count", quantity, True
        return "count", quantity, False

    @staticmethod
    def _normalize_name(name: str) -> str:
        return " ".join(name.split()).strip().lower()

    @staticmethod
    def _available_for_type(buckets: InventoryBuckets, req_type: str) -> float:
        if req_type == "g":
            return buckets.weight_g
        if req_type == "ml":
            return buckets.volume_ml
        return buckets.count

    @staticmethod
    def _decrement_bucket(buckets: InventoryBuckets, req_type: str, amount: float) -> None:
        if req_type == "g":
            buckets.weight_g = max(0.0, buckets.weight_g - amount)
        elif req_type == "ml":
            buckets.volume_ml = max(0.0, buckets.volume_ml - amount)
        else:
            buckets.count = max(0.0, buckets.count - amount)

    def _recompute_macros(self, candidate: PlanCandidate) -> tuple[Optional[Macros], List[str]]:
        total_weight = 0.0
        total_volume = 0.0
        total_count = 0.0
        for requirement in candidate.ingredients_required:
            if requirement.quantity_g:
                total_weight += float(requirement.quantity_g)
            if requirement.quantity_ml:
                total_volume += float(requirement.quantity_ml)
            if requirement.quantity_count:
                total_count += float(requirement.quantity_count)

        total_mass = total_weight + total_volume * 1.0 + total_count * _COUNT_TO_WEIGHT_G
        servings = max(1, int(candidate.servings or 1))
        if total_mass <= 0 or servings <= 0:
            return candidate.macros_per_serving, []

        per_serving_mass = total_mass / servings
        protein = per_serving_mass * _MACRO_PROTEIN_SHARE
        fat = per_serving_mass * _MACRO_FAT_SHARE
        carbs = max(0.0, per_serving_mass - protein - fat)
        macros = Macros(
            kcal=round(protein * 4 + carbs * 4 + fat * 9, 1),
            protein_g=round(protein, 1),
            carb_g=round(carbs, 1),
            fat_g=round(fat, 1),
        )

        diagnostics: list[str] = []
        if candidate.macros_per_serving is None:
            diagnostics.append("Estimated macros per serving from ingredient totals.")
            return macros, diagnostics

        delta = self._macro_delta(candidate.macros_per_serving, macros)
        if delta > 0.2:
            diagnostics.append("Adjusted macros per serving based on ingredient totals.")
            return macros, diagnostics

        return candidate.macros_per_serving, diagnostics

    @staticmethod
    def _macro_delta(existing: Macros, updated: Macros) -> float:
        fields = ("kcal", "protein_g", "carb_g", "fat_g")
        numerator = 0.0
        denominator = 0.0
        for field in fields:
            current = getattr(existing, field) or 0.0
            new = getattr(updated, field) or 0.0
            if current == 0 and new == 0:
                continue
            numerator += abs(current - new)
            denominator += max(current, new, 1.0)
        if denominator == 0:
            return 0.0
        return numerator / denominator

    def _add_diag(
        self,
        diagnostics: List[str],
        seen: Set[str],
        message: str,
        candidate_title: str,
    ) -> None:
        if not message or message in seen:
            return
        diagnostics.append(message)
        seen.add(message)
        logger.info("DiffValidator[%s] %s", candidate_title, message)
