"""Developer environment diagnostics."""

from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Sequence

Status = Literal["ok", "warn", "fail"]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VENV = PROJECT_ROOT / ".venv"


@dataclass(frozen=True)
class CheckResult:
    """Outcome of a developer-environment check."""

    name: str
    status: Status
    message: str


def _check_python() -> CheckResult:
    version = platform.python_version()
    if sys.version_info < (3, 11):
        return CheckResult(
            name="Python",
            status="fail",
            message=f"Detected {version}. Install Python 3.11 or newer.",
        )
    return CheckResult(name="Python", status="ok", message=f"Detected {version}")


def _check_virtualenv(venv_path: Path) -> CheckResult:
    if venv_path.exists():
        return CheckResult(
            name="Virtual environment",
            status="ok",
            message=f"Found at {venv_path}",
        )
    return CheckResult(
        name="Virtual environment",
        status="warn",
        message=f"Missing at {venv_path}. Run `make bootstrap` to create one.",
    )


def _check_env_file(project_root: Path) -> CheckResult:
    env_path = project_root / ".env"
    if env_path.exists():
        return CheckResult(
            name=".env file",
            status="ok",
            message=str(env_path),
        )
    return CheckResult(
        name=".env file",
        status="warn",
        message="Copy .env.example to .env to configure local secrets.",
    )


def _check_python_package(package: str, friendly_name: str | None = None) -> CheckResult:
    label = friendly_name or package
    if importlib.util.find_spec(package) is not None:
        return CheckResult(
            name=f"Python package: {label}",
            status="ok",
            message="available",
        )
    return CheckResult(
        name=f"Python package: {label}",
        status="warn",
        message=f"Install with `pip install {package}` or `make install-dev`.",
    )


def _check_command(label: str, candidates: Sequence[str]) -> CheckResult:
    for candidate in candidates:
        if shutil.which(candidate):
            return CheckResult(name=label, status="ok", message=f"found `{candidate}`")
    return CheckResult(
        name=label,
        status="warn",
        message=f"None of {', '.join(candidates)} found on PATH.",
    )


def _check_database_path(project_root: Path) -> CheckResult:
    from remy.config import get_settings

    settings = get_settings()
    path = settings.database_path
    if not path.is_absolute():
        path = (project_root / path).resolve()
    if path.exists() or path.parent.exists():
        return CheckResult(
            name="Database directory",
            status="ok",
            message=str(path.parent),
        )
    return CheckResult(
        name="Database directory",
        status="warn",
        message=f"Path {path.parent} does not exist (will be created on first run).",
    )


def _collect_checks(project_root: Path, venv_path: Path) -> list[CheckResult]:
    checks: list[CheckResult] = [
        _check_python(),
        _check_virtualenv(venv_path),
        _check_env_file(project_root),
        _check_python_package("pytest"),
        _check_python_package("ruff"),
        _check_python_package("mypy"),
        _check_command("Docker CLI", ["docker"]),
        _check_command("Docker Compose", ["docker-compose"]),
        _check_database_path(project_root),
    ]

    # If docker-compose standalone is missing but docker is present, treat as ok with plugin.
    docker_present = any(
        result.name == "Docker CLI" and result.status == "ok" for result in checks
    )
    compose_result = next(
        (result for result in checks if result.name == "Docker Compose"), None
    )
    if compose_result and compose_result.status == "warn" and docker_present:
        checks[checks.index(compose_result)] = CheckResult(
            name="Docker Compose",
            status="ok",
            message="available via `docker compose` plugin",
        )

    return checks


def format_report(results: Iterable[CheckResult]) -> str:
    """Render a human-readable report."""

    icon = {"ok": "✓", "warn": "⚠", "fail": "✖"}
    lines: list[str] = []
    counts = Counter()
    for result in results:
        counts[result.status] += 1
        lines.append(f"{icon[result.status]} {result.name}: {result.message}")
    lines.append("")
    lines.append(
        f"Summary: {counts['ok']} ok · {counts['warn']} warning(s) · {counts['fail']} failure(s)"
    )
    return "\n".join(lines)


def run_doctor(
    project_root: Path | None = None,
    venv_path: Path | None = None,
) -> tuple[int, str]:
    """Execute diagnostics and return (exit_code, report)."""

    # Avoid mutating PATH/working directory; prefer explicit roots.
    project_root = project_root or PROJECT_ROOT
    if not project_root.exists():
        project_root = Path.cwd()

    venv_path = venv_path or DEFAULT_VENV
    if not venv_path.is_absolute():
        venv_path = (project_root / venv_path).resolve()

    checks = _collect_checks(project_root=project_root, venv_path=venv_path)
    report = format_report(checks)
    exit_code = 1 if any(result.status == "fail" for result in checks) else 0
    return exit_code, report
