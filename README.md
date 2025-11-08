# Remy Dinner Planner

[![Kitchen CI](https://github.com/michaelasper/remy/actions/workflows/ci.yml/badge.svg)](https://github.com/michaelasper/remy/actions/workflows/ci.yml)
![Remy Approved](https://img.shields.io/badge/tiny%20chef-Remy%20approved-ff69b4?labelColor=4b275f)

Remy is a FastAPI + Vue sous-chef—named after the tiny rat from *Ratatouille*—that turns pantry data into daily dinner plans. It reads inventory, meals, and preferences from SQLite, proposes 2–3 options, and keeps the shopping list, receipts, and OCR pipeline in sync so your inner rodent chef can plate dinner on time.

## Quick Start

1. **Clone & install**
   ```bash
   git clone https://github.com/michaelasper/remy.git
   cd remy
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e .[dev]
   ```
2. **Install git hooks**
   ```bash
   git config core.hooksPath .githooks
   ```
   Every commit now runs `make lint` and `make typecheck`. Set `REMY_SKIP_GIT_HOOKS=1` to bypass in emergencies.
3. **Seed dependencies**
   ```bash
   make bootstrap      # optional helpers (lint/test targets)
   make llamacpp-setup # download default GGUF + start llama.cpp (once)
   ```
4. **Run the app**
   ```bash
   uvicorn remy.server.app:app --reload
   ```
   Visit `http://localhost:8000/` for the planner UI.  
   Use `Authorization: Bearer <REMY_API_TOKEN>` on protected endpoints.

5. **Generate a plan from the CLI**
   ```bash
   remy plan path/to/context.json --pretty
   ```

## Documentation

- [Overview & roadmap](docs/overview.md)
- [Setup & configuration details](docs/setup.md)
- [Testing strategy](docs/testing.md)
- [Release process & CLI image](docs/releases.md)
- More docs live inside `docs/`.

## License

MIT — see [`LICENSE`](LICENSE).
