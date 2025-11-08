# Remy Dinner Planner — Engineering Handoff

Context snapshot for the next contributor.

## Current State (Nov 7, 2025)

- **Planner UX**: `/` hosts a Vue 3 + Tailwind SPA. Planner tab now exposes a constraint form (date, attendees, time window) that calls `GET /planning-context` to assemble a JSON payload from SQLite (prefs, meals, inventory) before hitting `/plan`. Pretty recipe cards include serving-adjust toggles, inventory/shopping callouts, raw JSON toggle, “Add to Meals,” and buttons/automation that push shopping shortfalls straight into the shopping list.
- **Planner UX**: The form also offers per-run diet/allergen/max-time/cuisine overrides plus a DuckDuckGo recipe-search toggle with keyword filters; every change flows through `/planning-context`, and the resulting options ride along with plan payloads for transparency.
- **Planning Context API**: `GET /planning-context` (auth required) leverages `assemble_planning_context()` to hydrate `PlanningContext` objects; constraints fetched from query params fall back to defaults.
- **Leftover Tracking**: SQLite-backed leftovers table + `/leftovers` CRUD API keep prepared portions in sync with the UI, and `assemble_planning_context()` now hydrates real leftovers instead of stubbing an empty list.
- **LLM Backend**: Docker Compose spins up `llamacpp` sidecar (`ghcr.io/ggerganov/llama.cpp:full`) at `http://llamacpp:11434/v1`. Planner defaults: `REMY_LLM_PROVIDER=openai`, `REMY_LLM_BASE_URL=http://llamacpp:11434/v1`, `REMY_LLM_MODEL=qwen2.5-0.5b-instruct-q4_k_m.gguf`. `REMY_RECIPE_SEARCH_ENABLED=1` opt-in fetches DuckDuckGo snippets via `duckduckgo-search` for prompt enrichment.
- **DuckDuckGo Search**: `src/remy/search/recipes.py` provides `search_recipes()`. `planner/app/planner.py` uses `_collect_recipe_snippets()` to add web inspiration to prompts when enabled.
- **Tests**: `pytest tests/planner/test_planner.py tests/integration/test_planning_context_endpoint.py` passes. New integration tests require auth headers (token auto-loaded from settings).
- **Shopping List UX**: `/shopping-list` tab lets households capture errands, reset the entire list, move purchased items into inventory with a single tap, and now receives LLM shortfalls automatically each time a plan is generated. Backed by `/shopping-list*` endpoints + SQLite table so it works offline-first.
- **Receipt LLM**: OCR parsing now optionally routes through the configured LLM to clean up line items before they become suggestions; enable via `REMY_RECEIPT_LLM_ENABLED=1`.
- **Im2Recipe RAG**: Optional retrieval layer downloads `im2recipe_model.t7`, converts Recipe1M exports via `python -m remy.rag.recipe1m`, builds an Annoy index (`make rag-build-index`), and injects the top-k matches into planner prompts.
- **Diff & Validator**: Planner outputs run through `DiffValidator`, which clamps inventory deltas to on-hand stock, injects shopping shortfalls for missing/insufficient ingredients, and keeps plan payloads consistent with the assembled context.

## Recent Changes

1. Added dynamic planning-context assembly (`src/remy/planner/context_builder.py`) + API endpoint; Vue planner form now uses this flow instead of manual JSON editing.
2. Implemented a recipe-style plan viewer with serving size scaling and raw JSON toggle.
3. Introduced DuckDuckGo search opt-in, prompt hardening, and llama.cpp entrypoint script; Compose defaults updated accordingly.
4. Added integration tests covering `/planning-context`; docs updated to describe new env vars and workflow.
5. Landed the shopping list feature (SQLite table, REST endpoints, Vue tab) with reset + add-to-inventory flows and new tests.
6. Wired receipts into the LLM stack so OCR suggestions can be enhanced (new `REMY_RECEIPT_LLM_*` knobs, parser merge logic, and tests).
7. Added im2recipe-based RAG scaffolding (download helper, hashed retrieval, planner prompt integration, seed corpus, and unit tests).
8. Added Recipe1M conversion script + Annoy-backed indexing pipeline so large corpora stay fast.
9. Auto-add shopping shortfalls to the shopping list UI and implemented context-aware diffing so `inventory_deltas`/`shopping_shortfall` match reality.
10. Landed leftovers CRUD (SQLite + FastAPI) and wired the planner context so leftover utilization rules have real data.
11. Added planner-form overrides (diet, allergens, max prep time, preferred cuisines) that flow through `/planning-context` without mutating saved preferences.
12. Diff & Validator now supports imperial/volume conversions, heuristic macro recomputation, and per-candidate diagnostics rendered in the UI/logs.
13. Planner search controls landed: UI toggle + keyword filter feed `/planning-context`, and the planner respects the new `planner_options` contract end-to-end.
14. Planner shortfalls now sync straight into the shopping list API and the UI nudges users when unchecked items linger for days.
15. RAG/LLM observability added: snippet telemetry logs search hits (web/RAG) and diet/allergen checks, plus post-plan logs show which RAG inspirations were actually used.

## Next Steps / Ideas

- **Leftover Lifecycle**: Add decay/auto-archive heuristics (age-based nudges, auto-dismiss when consumed) and tighter UI surfacing now that leftovers are persisted.
- **Context Form Observability**: Surface which overrides were applied (and their source) in both the UI and logs, and add presets/history for common combinations.
- **Diagnostics Telemetry**: Persist Diff & Validator diagnostics (unknown units, macro adjustments, clamp events) so we can trend planner quality over time.
- **Search Telemetry**: Capture when per-plan search is enabled, which keywords were used, and whether snippets were returned to inform future defaults/presets.
- **LLM Observability**: Plumb the new logs into metrics/dashboards so we can visualize snippet usage, fallback rates, and diet/allergen hits over time.
- **Shopping Nudges**: Extend the new reminder system with auto-dismiss/acknowledge flows and optionally notify via push/Home Assistant when urgent items aren't checked off.
- **OCR Feedback Loop**: Log which suggestions originated from the LLM-assisted parser vs. heuristics so we can tune prompts and know when to fallback.
- **RAG Corpus Tuning**: Use the new RAG observability data to prune low-signal documents, auto-adjust top-k, and surface metrics in dashboards.
- **Diff Telemetry**: Emit metrics/logs when inventory deltas are clamped or when auto-added shortfalls occur so we can monitor planner quality.

## Testing / Dev Tips

- Run `docker compose up -d --build` to start API + llama.cpp. Use `make llamacpp-setup` on first boot to seed GGUF weights.
- Planner auth relies on `REMY_API_TOKEN`; UI stores token in localStorage. Include `Authorization: Bearer <token>` for `/planning-context` and `/plan` when testing via curl/postman.
- To verify planner outputs quickly: `curl -H 'Authorization: Bearer dev-local-token' -H 'Content-Type: application/json' -d '{...}' http://127.0.0.1:8000/plan | jq`.
- To confirm context assembly: `curl -H 'Authorization: Bearer dev-local-token' 'http://127.0.0.1:8000/planning-context?date=2025-11-07&attendees=2' | jq`.

## Key Files

- `docker-compose.yml`, `docker/llamacpp-entrypoint.sh`: llama.cpp sidecar config & startup script.
- `src/remy/planner/context_builder.py`: DB-driven context assembly logic.
- `src/remy/server/app.py`: new `/planning-context` endpoint + router wiring.
- `src/remy/server/templates/webui.html`: updated planner UI, recipe cards, Vue methods.
- `src/remy/planner/app/planner.py`: prompt templates, DuckDuckGo snippet injection.
- `tests/integration/test_planning_context_endpoint.py`: coverage for new endpoint.
- `src/remy/db/shopping_list.py`, `tests/integration/test_shopping_list_endpoint.py`: SQLite-backed shopping list feature + API coverage (with UI wiring in `webui.html`).
- `src/remy/db/leftovers.py`, `tests/integration/test_leftovers_endpoint.py`: leftover persistence layer + CRUD API coverage now powering planner context hydration.
- `src/remy/ocr/llm_client.py`, `src/remy/ocr/parser.py`, `tests/ocr/test_parser.py`: LLM-enhanced receipt parsing and accompanying tests.
- `src/remy/rag/im2recipe.py`, `src/remy/rag/build_index.py`, `src/remy/rag/recipe1m.py`, `tests/rag/test_im2recipe.py`, `tests/rag/test_recipe1m.py`: im2recipe download helpers, Annoy-backed retrieval, Recipe1M conversion, and accompanying CLIs/tests.
- `src/remy/agents/diff_validator.py`, `tests/agents/test_diff_validator.py`: context-aware diff/validation pass that normalizes inventory deltas, expands unit conversions, recomputes macros, and emits planner diagnostics.

Please keep this handoff file updated with each major change so incoming agents can ramp quickly.
