"""Command-line interface for Remy."""

from __future__ import annotations

import json
from typing import Optional

import typer

from remy.planner.app.planner import generate_plan
from remy.models.context import PlanningContext

app = typer.Typer(help="Remy dinner-planning automation commands.")


@app.command()
def plan(context_path: str, pretty: bool = typer.Option(False, "--pretty", help="Pretty-print output JSON.")) -> None:
    """
    Generate dinner plan candidates for the provided planning context JSON file.
    """
    with open(context_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    context = PlanningContext.model_validate(payload)
    plan = generate_plan(context)
    as_dict = plan.model_dump()

    if pretty:
        typer.echo(json.dumps(as_dict, indent=2, sort_keys=True))
    else:
        typer.echo(json.dumps(as_dict))


def main(argv: Optional[list[str]] = None) -> None:
    """Entry point for `python -m remy`."""
    app(prog_name="remy", args=argv)


if __name__ == "__main__":
    main()
