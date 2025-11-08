# UI Screenshots

Remy ships a Playwright helper to grab deterministic UI screenshots — handy for README updates or release notes.

## Requirements

- `pip install -e .[dev]` (installs Playwright)
- One-time browser install:
  ```bash
  python -m playwright install chromium
  ```
- A running Remy server (e.g., `docker compose up -d`).

## Capture a screenshot

```bash
scripts/capture_ui.py \
  --url http://localhost:8000/ \
  --output docs/images/remy-ui.png \
  --width 1280 --height 720 --delay 2
```

The defaults match the example above, so `scripts/capture_ui.py` is usually enough. The script waits for network idle, pauses briefly for Vue to finish rendering, and captures a full-page PNG.

Commit the refreshed `docs/images/remy-ui.png` when you want the README preview to reflect new UI changes.
