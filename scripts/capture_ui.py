#!/usr/bin/env python
"""Capture Remy UI screenshots via Playwright."""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

DEFAULT_URL = "http://localhost:8000/"
DEFAULT_OUT = pathlib.Path("docs/images/remy-ui.png")
DEFAULT_VIEWPORT = (1280, 720)
DEFAULT_DELAY = 2.0


def capture(url: str, output: pathlib.Path, viewport: tuple[int, int], delay: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
        page = context.new_page()
        page.goto(url, wait_until="networkidle")
        time.sleep(delay)
        page.screenshot(path=str(output), full_page=True)
        browser.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Capture Remy UI screenshot")
    parser.add_argument("--url", default=DEFAULT_URL, help="Base URL of the running Remy UI")
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUT, help="Output PNG path")
    parser.add_argument("--width", type=int, default=DEFAULT_VIEWPORT[0], help="Viewport width")
    parser.add_argument("--height", type=int, default=DEFAULT_VIEWPORT[1], help="Viewport height")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Seconds to wait after load")
    args = parser.parse_args(argv)

    capture(args.url, args.output, (args.width, args.height), args.delay)
    print(f"Saved screenshot to {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
