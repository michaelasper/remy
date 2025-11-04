"""HTML template loading utilities for Remy web UI."""

from importlib import resources


def load(name: str) -> str:
    """Return the contents of a template file bundled with the package."""

    return resources.files(__name__).joinpath(name).read_text(encoding="utf-8")
