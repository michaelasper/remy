"""Basic smoke tests for scaffolding."""

from datetime import date

from remy.models.context import PlanningContext
from remy.planner.app.planner import generate_plan


def test_generate_plan_returns_plan() -> None:
    context = PlanningContext(date=date.today())
    plan = generate_plan(context)

    assert plan.date == context.date
    assert isinstance(plan.candidates, list)
