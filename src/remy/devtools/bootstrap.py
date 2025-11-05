"""Virtual environment bootstrapper."""

from __future__ import annotations

import os
import subprocess
import venv
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _run(cmd: Sequence[str], cwd: Path | None = None) -> None:
    subprocess.check_call(cmd, cwd=str(cwd) if cwd else None)


def run_bootstrap(
    venv_dir: Path | None = None,
    install: bool = True,
    upgrade_pip: bool = True,
    project_root: Path | None = None,
) -> int:
    """Create (or reuse) a project virtual environment."""

    project_root = project_root or PROJECT_ROOT
    venv_dir = (venv_dir or PROJECT_ROOT / ".venv").resolve()

    if venv_dir.exists():
        print(f"Using existing virtual environment at {venv_dir}")
    else:
        print(f"Creating virtual environment at {venv_dir}")
        builder = venv.EnvBuilder(with_pip=True, clear=False)
        builder.create(venv_dir)

    python_executable = _venv_python(venv_dir)
    if not python_executable.exists():
        print("Virtual environment seems corrupted; recreating.")
        builder = venv.EnvBuilder(with_pip=True, clear=True)
        builder.create(venv_dir)
        python_executable = _venv_python(venv_dir)

    commands: list[list[str]] = []
    if upgrade_pip:
        commands.append(
            [str(python_executable), "-m", "pip", "install", "--upgrade", "pip"]
        )
    if install:
        commands.append(
            [str(python_executable), "-m", "pip", "install", "-e", ".[dev,server]"]
        )

    try:
        for command in commands:
            print(f"Running: {' '.join(command)}")
            _run(command, cwd=project_root)
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}: {' '.join(exc.cmd)}")
        return exc.returncode

    posix_hint = f"source {python_executable.parent}/activate"
    windows_hint = f"{venv_dir}\\Scripts\\activate"
    print("Bootstrap complete.")
    print(f"- POSIX activate: {posix_hint}")
    print(f"- Windows activate: {windows_hint}")
    print(f"- Interpreter: {python_executable}")
    return 0
