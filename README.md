# Remy Dinner Planner

Remy is a multi-agent automation platform that assembles a daily dinner plan for a household. It gathers context from inventories and recent meals, generates candidate menus tailored to dietary preferences, highlights missing ingredients, and coordinates notifications and approvals so meals stay varied, timely, and low waste.

## Key Capabilities

- Build a rich planning context from SQLite data, pantry leftovers, and household preferences.
- Override diet, allergens, prep time, and cuisine constraints per run directly from the planner form without touching saved preferences.
- Flip DuckDuckGo recipe search on/off per plan and steer it with custom keywords for inspiration when needed.
- Emit LLM observability logs covering recipe snippet usage, RAG hits, and diet/allergen checks so constraint regressions are visible immediately.
- Track RAG retrieval hits and log which inspirations make it into final meals to guide corpus/index tuning.
- Sync planner shopping shortfalls directly into the shopping list and surface reminders when unchecked items linger too long.
- Propose two to three balanced dinner candidates per day with prep time, servings, steps, and macros.
- Normalize ingredient data, detect shopping shortfalls, and update the inventory after approval.
- Surface planner diagnostics (unit fallbacks, macro estimates, constraint overrides) directly in the UI so humans can trust automated adjustments.
- Manage a shared shopping list with instant reset controls and one-tap inventory sync once groceries are in hand.
- Enrich LLM prompts with retrieval-augmented recipe snippets seeded by the im2recipe model.
- Notify the household by 15:00 local time and dispatch any required shopping list updates.

## Getting Started

- Install Python 3.11 (use `pyenv install 3.11.9` and respect `.python-version`, or spin up `.venv` via `python3 -m venv .venv && source .venv/bin/activate`).
- Install dependencies with `pip install -e .[dev]` after activating your environment; add server extras with `pip install -e .[server]` if you plan to run Uvicorn directly.
- Install Tesseract OCR locally (`brew install tesseract` on macOS, `sudo apt-get install tesseract-ocr` on Debian/Ubuntu). The project Docker image installs Tesseract and Poppler so OCR works inside Docker/Compose without extra steps.
- Install Poppler utilities for PDF support (`brew install poppler` or `sudo apt-get install poppler-utils`) so `pdf2image` can rasterize multi-page receipts.
- Configure `REMY_OCR_ARCHIVE_PATH` (defaults to `./data/receipts_archive`) if you want processed receipt blobs archived outside SQLite.
- Prometheus metrics are exposed at `/metrics`; scrape the endpoint to monitor request latency, OCR throughput, and ingestion counts.
- Run the smoke test suite with `pytest` to validate the scaffolding.
- Execute `remy plan path/to/context.json --pretty` to generate placeholder plans from a context payload.
- Launch the API with `uvicorn remy.server.app:app --reload` and POST planning contexts to `/plan`.
- Open `http://localhost:8000/` for the Vue-based control center covering planner, inventory, the new shopping list, preferences, and receipts.
- Build and run a containerized server with `docker build -t remy .` followed by `docker run -p 8000:8000 remy` or `docker-compose up --build -d`.
- The Docker Compose stack now ships with a [llama.cpp](https://github.com/ggerganov/llama.cpp) sidecar (via `llama-cpp-python`) on port `11434`. Run `make llamacpp-setup` (or `docker compose up -d llamacpp`) to start the service; it automatically downloads the default Qwen2.5 0.5B Instruct GGUF the first time it boots. Remy injects `REMY_LLM_PROVIDER=openai`, `REMY_LLM_BASE_URL=http://llamacpp:11434/v1`, and `REMY_LLM_MODEL=qwen2.5-0.5b-instruct-q4_k_m.gguf`, so the planner talks to the sidecar out of the box. To use another OpenAI-compatible endpoint (vLLM/TGI/managed APIs) or Ollama, override the `REMY_LLM_*` variables (plus `LLAMACPP_*` if you want a different GGUF/ctx size) and restart the stack.
- Opt-in internet search: set `REMY_RECIPE_SEARCH_ENABLED=1` (and optionally `REMY_RECIPE_SEARCH_RESULTS=5`) to let the planner hit DuckDuckGo via the `duckduckgo-search` client, capturing fresh recipe snippets that are injected into the LLM prompt for richer variety.
- Use `make bootstrap` to create/update `.venv`, `make doctor` to sanity-check local tooling, and `make install-dev`, `make test`, `make check`, or `make run-server` (set `DURATION=5` for a temporary run). The Makefile auto-detects `.venv/bin/python` when present.
- Generate coverage reports with `make coverage` (requires the `dev` extras).
- Prefer a reproducible environment via `.devcontainer/devcontainer.json` (VS Code Dev Containers / `devcontainer up`) when collaborating.
- Upload raw receipt images with `POST /receipts` (multipart form); list metadata with `GET /receipts`, check OCR status with `GET /receipts/{id}/ocr`, trigger extraction with `POST /receipts/{id}/ocr`, and download files via `/receipts/{id}/download`. The control center also lets you upload, process, and preview receipts.
- Run `make ocr OCR_RECEIPT_ID=<id>` or `remy receipt-ocr <id>` to process stored receipts from the CLI. The long-running worker can be started with `make ocr-worker` (accepts `ARGS="--poll-interval 2 --batch-size 3"`) or `remy ocr-worker`.
- Run Docker-based end-to-end checks with `RUN_E2E=1 pytest tests/e2e` or `make test-e2e` (Docker & Docker Compose required).

## System Architecture

Remy is organized as a collection of focused agents that collaborate through shared JSON contracts:

| Agent | Role | Primary Inputs | Main Outputs | Notes |
| --- | --- | --- | --- | --- |
| Context Assembler | Gather all data needed for planning. | SQLite (inventory, meals, preferences), leftovers | `planning_context.json` | Prepares structured context for the planner, honors per-run overrides, and carries recipe-search toggles/keywords. |
| Menu Planner | Design candidate meal plans. | `planning_context.json` | Plan JSON | Starts with a mocked planner; upgrades to a local LLM (llama.cpp/vLLM/Ollama) later. |
| Diff & Validator | Canonicalize ingredients and compute shortages. | Planner output, inventory DB | Normalized plan, `shopping_shortfall` | Clamps deltas, expands units (kg/lb/cups), recomputes macros, and emits diagnostics for the UI/logs. |
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
- **LLM Runtime**: `generate_plan(context_json)` entry point, backed by the bundled llama.cpp sidecar (OpenAI-compatible) with optional fallbacks to Ollama or vLLM.
- **Home Assistant**: Notifications via `/api/services/persistent_notification/create` and shopping list sync via `/api/shopping_list/item`.
- **Scheduler**: APScheduler triggers the planning pipeline at 15:00 local time.
- **Web UI (planned)**: `/plan/today` viewer with a future `/plan/approve` endpoint for approvals.

## Receipt OCR MVP

1. Upload receipts from the control center or `POST /receipts`. Each upload stores raw bytes plus a pending OCR record.
2. Inspect status via `GET /receipts/{id}/ocr` or the Receipts tab, which now shows progress, confidence, errors, and bounding boxes.
3. Trigger extraction with the UI “Run OCR” button, `POST /receipts/{id}/ocr`, `remy receipt-ocr <id>`, `make ocr OCR_RECEIPT_ID=<id>`, or let the background worker handle it automatically.
4. The pipeline (`ReceiptOcrService`) preprocesses each page (grayscale, denoise, deskew), handles multi-page PDFs via `pdf2image`, and persists structured text/metadata (word boxes, per-page confidence) in the `receipt_ocr_results` table.
5. Run the daemon-style worker (`remy ocr-worker` or enable `REMY_OCR_WORKER_ENABLED=true`) to poll and process staged receipts continuously. APScheduler drives the worker so batches run at `REMY_OCR_WORKER_POLL_INTERVAL` cadence without their own thread.
6. Parsed metadata now includes store/date heuristics and normalized line items (`metadata.parsed`), with fuzzy-matched inventory IDs when confidence is high. Sensitive number strings (e.g., payment PANs) are masked before persistence.
7. Once OCR finishes the service automatically ingests high-confidence line items into inventory; anything ambiguous lands in **Pending Suggestions** for manual review via `/inventory/suggestions` or the Receipts tab.
8. Use the Receipts tab to review parsed line items: tweak quantities, deselect anything irrelevant, and click **Approve Selected** to add or update inventory entries. Dismiss or approve queued suggestions from the Inventory tab when needed.
9. Raw binaries are compressed to `REMY_OCR_ARCHIVE_PATH` once OCR succeeds so the receipts table stays lean, and the metadata continues to serve the sanitized text.
10. Review and copy the extracted text directly in the UI for auditing.
11. Track meal outcomes in the Meals dashboard (`/meals`), leaving ratings and notes to inform future planning.

*Limitations*: ensure Tesseract and Poppler executables are present locally (or run inside the Docker image). Bounding boxes are limited to the first 1,000 words to keep payload sizes manageable.

Set `REMY_OCR_WORKER_ENABLED=true` (plus optional `REMY_OCR_WORKER_POLL_INTERVAL`, `REMY_OCR_WORKER_BATCH_SIZE`, and `REMY_OCR_LANG`) to run the worker automatically when the FastAPI app boots.

### LLM-Assisted Receipt Parsing

Remy can now pass OCR text through the same OpenAI-compatible runtime you point the planner at. Flip `REMY_RECEIPT_LLM_ENABLED=1` (optionally override `REMY_RECEIPT_LLM_BASE_URL`, `_MODEL`, `_PROVIDER`, `_TEMPERATURE`, `_MAX_TOKENS`) to let the LLM clean up item names, infer quantities, and add missing lines before they become suggestions. When the dedicated receipt variables are unset, the system reuses `REMY_LLM_*` so the bundled llama.cpp sidecar works out of the box.

### Im2Recipe Retrieval-Augmented Generation

- Run `make rag-setup` (or `python -m remy.rag.setup`) once to download and decompress `im2recipe_model.t7.gz` into `./data/models/im2recipe_model.t7`. The artifact is ignored by Git and only lives on your machine.
- To ingest the full Recipe1M dataset, download the official export, then run `python -m remy.rag.recipe1m --input ~/Downloads/recipes_raw_nosource_fn.json.gz --output data/rag/recipes_recipe1m.json --limit 50000` (adjust limit to taste). Point `REMY_RAG_CORPUS_PATH` at the generated JSON file.
- Build or refresh the Annoy index with `make rag-build-index` (uses `REMY_RAG_INDEX_PATH`, `REMY_RAG_INDEX_TREES`, and `REMY_RAG_EMBEDDING_DIM`), then export `REMY_RAG_ENABLED=1` so the planner prompt automatically receives the top-k matches.
- Retrieval uses a feature-hashing embedding salted by the im2recipe model bytes, and the Annoy index keeps lookups fast even when the corpus grows to tens of thousands of recipes.

## Shopping List Flow

1. Query the current checklist with `GET /shopping-list` (unauthenticated by default for quick mobile access). The Vue control center surfaces the same data in the **Shopping List** tab with large tap targets for aisle use.
2. Add items via `POST /shopping-list` (name with optional quantity/unit/notes). The UI mirrors this as a compact form so you can capture errands on the fly.
3. Toggle completion with `PUT /shopping-list/{id}` (`is_checked` true/false) or tap the checkbox in the UI. `DELETE /shopping-list/{id}` removes an entry if plans change.
4. Use `POST /shopping-list/reset` to clear the entire list at the end of a run—this powers the “Reset List” button in the UI.
5. When groceries are home, hit `POST /shopping-list/{id}/add-to-inventory` (or tap “Add to Inventory” in the UI). The endpoint creates a matching inventory record and automatically deletes the shopping entry, keeping the loop tight between errands and pantry reality.

## Implementation Notes

- Start implementation with `planner/app/planner.py::generate_plan()`, ensuring outputs pass the `models.Plan` schema validation.
- Next milestone focuses on `/plan/approve` to persist approvals and manage inventory mutations.
- All persistent data remains local; API tokens should be stored in a `.env` file kept out of version control.
- SQLite persistence lives at `data/remy.db` by default; the first run seeds `inventory_items` from `inventory_snapshot.json` (or built-in defaults) via the repository layer in `src/remy/db/`. Uploaded receipts are stored in the `receipts` table alongside their binary payloads for future OCR.
- Set `REMY_API_TOKEN` to require authenticated requests for `/plan` and inventory/preferences mutations (Bearer, `X-API-Key`, or `api_token` query support).
- Set `REMY_LOG_LEVEL` (default `INFO`, local `.env` uses `DEBUG`) alongside `REMY_LOG_FORMAT` (`plain` or `json`) to control server logging.
- Toggle per-request access logging with `REMY_LOG_REQUESTS` (defaults to `true`). Each response now carries an `X-Request-ID`, and logs redact API/Home Assistant tokens automatically.
- When using remote LLMs, redact personally identifiable household details.

## Testing Strategy

- **Unit Tests**: Validate inventory diffing, normalization logic, and approval mutations.
- **Schema Tests**: Verify JSON payloads against `models.Plan` and related contracts.
- **Integration Tests**: Mock Home Assistant APIs to ensure notifications and shopping list updates behave as expected.
- **API Integration Tests**: Use FastAPI's `TestClient` (see `tests/integration/test_plan_endpoint.py`) to validate dependency overrides and response contracts.
- **Snapshot Tests**: Run fixed planning contexts to confirm deterministic planner output across revisions.
- **End-to-End**: Launch the Docker Compose stack and verify the planner endpoint via `tests/e2e/test_compose_plan.py` (requires `RUN_E2E=1`).
- **Security Tests**: `tests/integration/test_security.py` ensures API token validation gates state-changing endpoints.

## Roadmap

1. MVP: mock planner, manual CSV imports, Home Assistant notifications.
2. LLM Integration: connect to llama.cpp (default), Ollama, or vLLM for richer plan generation.
3. RAG Recipe Corpus: embed 100–300 local recipes for retrieval-augmented planning.
4. Receipt OCR/email ingestion for automatic inventory updates.
5. Nutrition scoring, variety tracking, and advanced preference learning.

## Contributing

The project is in its early stages and welcomes contributions focused on building out the agent implementations, improving test coverage, and expanding Home Assistant integrations. Please propose changes via pull requests and maintain deterministic, schema-validated outputs across agents.

## License

This project is released under the MIT License. See `LICENSE` for the full text.
