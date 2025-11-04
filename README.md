# Remy Dinner Planner

Remy is a multi-agent automation platform that assembles a daily dinner plan for a household. It gathers context from inventories and recent meals, generates candidate menus tailored to dietary preferences, highlights missing ingredients, and coordinates notifications and approvals so meals stay varied, timely, and low waste.

## Key Capabilities

- Build a rich planning context from SQLite data, pantry leftovers, and household preferences.
- Propose two to three balanced dinner candidates per day with prep time, servings, steps, and macros.
- Normalize ingredient data, detect shopping shortfalls, and update the inventory after approval.
- Notify the household by 15:00 local time and dispatch any required shopping list updates.

## Getting Started

- Install Python 3.11 (use `pyenv install 3.11.9` and respect `.python-version`, or spin up `.venv` via `python3 -m venv .venv && source .venv/bin/activate`).
- Install dependencies with `pip install -e .[dev]` after activating your environment; add server extras with `pip install -e .[server]` if you plan to run Uvicorn directly.
- Run the smoke test suite with `pytest` to validate the scaffolding.
- Execute `remy plan path/to/context.json --pretty` to generate placeholder plans from a context payload.
- Launch the API with `uvicorn remy.server.app:app --reload` and POST planning contexts to `/plan`.
- Open `http://localhost:8000/` for the interactive web UI that submits contexts to the API.
- Build and run a containerized server with `docker build -t remy .` followed by `docker run -p 8000:8000 remy`.
- Use `make install-dev`, `make test`, or `make run-server` (set `DURATION=5` for a temporary run). The Makefile auto-detects `.venv/bin/python` when present.
- Prefer a reproducible environment via `.devcontainer/devcontainer.json` (VS Code Dev Containers / `devcontainer up`) when collaborating.

## System Architecture

Remy is organized as a collection of focused agents that collaborate through shared JSON contracts:

| Agent | Role | Primary Inputs | Main Outputs | Notes |
| --- | --- | --- | --- | --- |
| Context Assembler | Gather all data needed for planning. | SQLite (inventory, meals, preferences), leftovers | `planning_context.json` | Prepares structured context for the planner. |
| Menu Planner | Design candidate meal plans. | `planning_context.json` | Plan JSON | Starts with a mocked planner; upgrades to a local LLM (Ollama/vLLM) later. |
| Diff & Validator | Canonicalize ingredients and compute shortages. | Planner output, inventory DB | Normalized plan, `shopping_shortfall` | Ensures schema compliance and consistent naming. |
| Approvals Orchestrator | Handle human approval, mutations, and notifications. | Normalized plan | Approved meal, inventory updates | Applies changes transactionally. |
| Shopping Dispatcher | Sync shortfalls to shopping endpoints. | `shopping_shortfall` | Home Assistant API calls | Future integrations include Instacart and Amazon carts. |
| Receipt Ingestor | Update inventory from receipts. | CSV/email/OCR data | Inventory upserts | Enables passive inventory updates. |
| Nutrition Estimator | Calculate macros per serving. | Ingredient quantities | `macros_per_serving` | Optional extension for nutritional insights. |
| Notifier | Communicate plans and approvals. | Message payloads | Home Assistant notifications | Guarantees the household sees the plan on time. |

Planned future agents include calendar integration, preference learning, variety scheduling, and computer-vision pantry scanning.

## Shared Data Contracts

Two JSON payloads keep agents aligned:

- **Planning Context** – describes the current date, preferences, recent meals, inventory, leftovers, and constraints.
- **Plan (Normalized Output)** – enumerates candidate dinners with ingredients, inventory deltas, shopping shortfalls, and per-serving macros.

Both schemas favor deterministic, machine-validated data so downstream automation stays reliable.

## Daily Automation Flow

1. Context Assembler builds `planning_context.json`.
2. Menu Planner proposes dinner candidates.
3. Diff & Validator normalizes ingredients and identifies any shortages.
4. Approvals Orchestrator sends a summary via the Notifier.
5. On approval, inventory updates apply and Shopping Dispatcher pushes deltas to the household shopping list.

If the planner fails, the system reuses the most recent approved meal as a fallback.

## Integrations & Tooling

- **Database**: SQLite backing tables for inventory, meals, preferences, and ingredient metadata.
- **LLM Runtime**: `generate_plan(context_json)` entry point, initially mocked and later powered by Ollama or vLLM.
- **Home Assistant**: Notifications via `/api/services/persistent_notification/create` and shopping list sync via `/api/shopping_list/item`.
- **Scheduler**: APScheduler triggers the planning pipeline at 15:00 local time.
- **Web UI (planned)**: `/plan/today` viewer with a future `/plan/approve` endpoint for approvals.

## Implementation Notes

- Start implementation with `planner/app/planner.py::generate_plan()`, ensuring outputs pass the `models.Plan` schema validation.
- Next milestone focuses on `/plan/approve` to persist approvals and manage inventory mutations.
- All persistent data remains local; API tokens should be stored in a `.env` file kept out of version control.
- When using remote LLMs, redact personally identifiable household details.

## Testing Strategy

- **Unit Tests**: Validate inventory diffing, normalization logic, and approval mutations.
- **Schema Tests**: Verify JSON payloads against `models.Plan` and related contracts.
- **Integration Tests**: Mock Home Assistant APIs to ensure notifications and shopping list updates behave as expected.
- **API Integration Tests**: Use FastAPI's `TestClient` (see `tests/integration/test_plan_endpoint.py`) to validate dependency overrides and response contracts.
- **Snapshot Tests**: Run fixed planning contexts to confirm deterministic planner output across revisions.

## Roadmap

1. MVP: mock planner, manual CSV imports, Home Assistant notifications.
2. LLM Integration: connect to Ollama/vLLM for richer plan generation.
3. RAG Recipe Corpus: embed 100–300 local recipes for retrieval-augmented planning.
4. Receipt OCR/email ingestion for automatic inventory updates.
5. Nutrition scoring, variety tracking, and advanced preference learning.

## Contributing

The project is in its early stages and welcomes contributions focused on building out the agent implementations, improving test coverage, and expanding Home Assistant integrations. Please propose changes via pull requests and maintain deterministic, schema-validated outputs across agents.

## License

This project is released under the MIT License. See `LICENSE` for the full text.
