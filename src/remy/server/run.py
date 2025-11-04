"""Helper for running the Remy ASGI application via Makefile."""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import uvicorn


async def _serve_with_duration(server: uvicorn.Server, duration: float) -> None:
    """Run the server and shut it down after the specified duration."""

    async def _shutdown() -> None:
        await asyncio.sleep(duration)
        server.should_exit = True

    asyncio.create_task(_shutdown())
    await server.serve()


def _parse_duration(value: str | None) -> Optional[float]:
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid REMY_SERVER_DURATION '{value}': {exc}") from exc
    if parsed <= 0:
        raise SystemExit("REMY_SERVER_DURATION must be greater than 0 when provided.")
    return parsed


def main() -> None:
    """Entry point used by `make run-server`."""

    host = os.environ.get("REMY_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("REMY_SERVER_PORT", "8000"))
    reload_enabled = os.environ.get("RELOAD") == "1"
    duration = _parse_duration(os.environ.get("REMY_SERVER_DURATION"))

    if reload_enabled and duration is not None:
        raise SystemExit("Use RELOAD=0 when specifying REMY_SERVER_DURATION.")

    if reload_enabled:
        uvicorn.run(
            "remy.server.app:app",
            host=host,
            port=port,
            reload=True,
        )
        return

    config = uvicorn.Config(
        "remy.server.app:app",
        host=host,
        port=port,
        reload=False,
        factory=False,
    )
    server = uvicorn.Server(config)

    if duration is not None:
        asyncio.run(_serve_with_duration(server, duration))
        return

    server.run()


if __name__ == "__main__":
    main()
