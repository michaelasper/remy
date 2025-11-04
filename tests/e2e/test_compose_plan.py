"""End-to-end test that exercises the Docker Compose stack."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import date
from pathlib import Path

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
DOCKER_ENV = os.environ.get("DOCKER", "docker")
COMPOSE_ENV = os.environ.get("COMPOSE", "docker-compose")
DOCKER_EXECUTABLE = shutil.which(DOCKER_ENV.split()[0])
COMPOSE_EXECUTABLE = shutil.which(COMPOSE_ENV.split()[0])

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_E2E") != "1",
    reason="Set RUN_E2E=1 to enable Docker Compose end-to-end tests.",
)


def _compose_command(*args: str) -> list[str]:
    return COMPOSE_ENV.split() + list(args)


@pytest.fixture(scope="session")
def compose_stack() -> None:
    if DOCKER_EXECUTABLE is None and COMPOSE_EXECUTABLE is None:
        pytest.skip("Neither docker nor compose executable found in PATH.")
    if not COMPOSE_FILE.exists():
        pytest.skip("docker-compose.yml not present; cannot run e2e test.")

    version_cmd = _compose_command("version")
    version_proc = subprocess.run(
        version_cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if version_proc.returncode != 0:
        pytest.skip(
            "Docker Compose not available: "
            f"{version_proc.stderr.strip() or version_proc.stdout.strip()}"
        )

    up_cmd = _compose_command("up", "-d", "--build")
    subprocess.run(up_cmd, check=True, cwd=PROJECT_ROOT)

    try:
        yield
    finally:
        down_cmd = _compose_command("down", "--remove-orphans", "-v")
        subprocess.run(down_cmd, check=False, cwd=PROJECT_ROOT)


def wait_for_service(url: str, timeout: float = 60.0) -> httpx.Response:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = httpx.post(url, json={"date": str(date.today())}, timeout=5.0)
            if response.status_code == 200:
                return response
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise AssertionError(f"Timed out waiting for service at {url}")


def test_plan_endpoint_via_compose(compose_stack: None) -> None:
    """Verify the planner endpoint responds when launched via Docker Compose."""

    response = wait_for_service("http://127.0.0.1:8000/plan")
    payload = response.json()

    assert "date" in payload
    assert "candidates" in payload
