"""CLI entrypoint for developer tools."""

from __future__ import annotations

from pathlib import Path

import typer

from .bootstrap import run_bootstrap
from .doctor import run_doctor

app = typer.Typer(help="Developer productivity commands for the Remy project.")


@app.command()
def doctor() -> None:
    """Inspect the local environment and report potential issues."""

    exit_code, report = run_doctor()
    typer.echo(report)
    raise typer.Exit(code=exit_code)


@app.command()
def bootstrap(
    venv_path: Path = typer.Option(
        Path(".venv"),
        "--venv-path",
        help="Location of the virtual environment to create or reuse.",
    ),
    no_install: bool = typer.Option(
        False,
        "--no-install",
        help="Create the virtual environment without installing project dependencies.",
    ),
    no_upgrade: bool = typer.Option(
        False,
        "--no-upgrade",
        help="Skip upgrading pip in the virtual environment.",
    ),
) -> None:
    """Create or update the local virtual environment."""

    exit_code = run_bootstrap(
        venv_dir=venv_path,
        install=not no_install,
        upgrade_pip=not no_upgrade,
    )
    raise typer.Exit(code=exit_code)


def main() -> None:
    """Execute the Typer application."""

    app()
