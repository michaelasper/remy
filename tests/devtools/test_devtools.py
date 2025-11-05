"""Tests for developer tooling utilities."""

from __future__ import annotations

import os

from remy.devtools.bootstrap import run_bootstrap
from remy.devtools.doctor import run_doctor


def test_doctor_generates_report():
    exit_code, report = run_doctor()
    assert exit_code == 0
    assert "Python" in report
    assert "Summary" in report


def test_bootstrap_creates_virtualenv(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    project_root.mkdir()
    # Create minimal pyproject and package structure to satisfy editable install if requested.
    (project_root / "pyproject.toml").write_text(
        "[build-system]\nrequires=[]\nbuild-backend='setuptools.build_meta'\n"
    )
    package_dir = project_root / "src" / "dummy"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("")

    venv_dir = project_root / ".venv"
    exit_code = run_bootstrap(
        venv_dir=venv_dir,
        install=False,
        upgrade_pip=False,
        project_root=project_root,
    )
    assert exit_code == 0

    bin_dir = "Scripts" if os.name == "nt" else "bin"
    python_path = venv_dir / bin_dir / ("python.exe" if os.name == "nt" else "python")
    assert python_path.exists()
