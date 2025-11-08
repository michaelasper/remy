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
  --width 1600 --height 900 --delay 2 --scale 1.5
```

Omit the flags if you're happy with those defaults. Pass `--full-page` when you want the entire scroll height; otherwise it captures just the viewport to keep screenshots readable.

Commit the refreshed `docs/images/remy-ui.png` when you want the README preview to reflect new UI changes.
