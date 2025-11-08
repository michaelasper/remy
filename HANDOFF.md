# Remy Dinner Planner — Engineering Handoff

Context snapshot for the next contributor.

## Current State (Nov 7, 2025)

- **Planner UX**: `/` hosts a Vue 3 + Tailwind SPA. Planner tab now exposes a constraint form (date, attendees, time window) that calls `GET /planning-context` to assemble a JSON payload from SQLite (prefs, meals, inventory) before hitting `/plan`. Pretty recipe cards include serving-adjust toggles, inventory/shopping callouts, and raw JSON toggle.
- **Planning Context API**: `GET /planning-context` (auth required) leverages `assemble_planning_context()` to hydrate `PlanningContext` objects; constraints fetched from query params fall back to defaults.
- **LLM Backend**: Docker Compose spins up `llamacpp` sidecar (`ghcr.io/ggerganov/llama.cpp:full`) at `http://llamacpp:11434/v1`. Planner defaults: `REMY_LLM_PROVIDER=openai`, `REMY_LLM_BASE_URL=http://llamacpp:11434/v1`, `REMY_LLM_MODEL=qwen2.5-0.5b-instruct-q4_k_m.gguf`. `REMY_RECIPE_SEARCH_ENABLED=1` opt-in fetches DuckDuckGo snippets via `duckduckgo-search` for prompt enrichment.
- **DuckDuckGo Search**: `src/remy/search/recipes.py` provides `search_recipes()`. `planner/app/planner.py` uses `_collect_recipe_snippets()` to add web inspiration to prompts when enabled.
- **Tests**: `pytest tests/planner/test_planner.py tests/integration/test_planning_context_endpoint.py` passes. New integration tests require auth headers (token auto-loaded from settings).
- **Shopping List UX**: `/shopping-list` tab lets households capture errands, reset the entire list, and move purchased items into inventory with a single tap. Backed by `/shopping-list*` endpoints + SQLite table so it works offline-first.
- **Receipt LLM**: OCR parsing now optionally routes through the configured LLM to clean up line items before they become suggestions; enable via `REMY_RECEIPT_LLM_ENABLED=1`.
- **Im2Recipe RAG**: Optional retrieval layer downloads `im2recipe_model.t7` on demand, hashes the recipe corpus, and injects the top-k matches into planner prompts.

## Recent Changes

1. Added dynamic planning-context assembly (`src/remy/planner/context_builder.py`) + API endpoint; Vue planner form now uses this flow instead of manual JSON editing.
2. Implemented a recipe-style plan viewer with serving size scaling and raw JSON toggle.
3. Introduced DuckDuckGo search opt-in, prompt hardening, and llama.cpp entrypoint script; Compose defaults updated accordingly.
4. Added integration tests covering `/planning-context`; docs updated to describe new env vars and workflow.
5. Landed the shopping list feature (SQLite table, REST endpoints, Vue tab) with reset + add-to-inventory flows and new tests.
6. Wired receipts into the LLM stack so OCR suggestions can be enhanced (new `REMY_RECEIPT_LLM_*` knobs, parser merge logic, and tests).
7. Added im2recipe-based RAG scaffolding (download helper, hashed retriever, planner prompt integration, seed corpus, and unit tests).

## Next Steps / Ideas

- **Leftovers Wiring**: `assemble_planning_context` currently hardcodes `leftovers=[]`. Add real leftover tracking table / API once available.
- **Context Form Enhancements**: Add UI controls to select diet/allergen overrides per run, or allow advanced constraint editing (e.g., max prep time, preferred cuisines).
- **Planner Validation**: Diff & Validator agent is still a stub. Consider using assembled context to auto-adjust LLM outputs (e.g., ensure inventory_deltas align with inventory).
- **Search Controls**: Add a UI toggle to enable/disable recipe search per plan or specify keywords.
- **LLM Observability**: Log snippet usage and track fallback rates to ensure the LLM honors vegan/gluten-free constraints consistently.
- **Shopping Automation**: Feed planner `shopping_shortfall` data directly into the shopping list tab/DB so shortages appear automatically, and surface friendly reminders when items linger unchecked.
- **OCR Feedback Loop**: Log which suggestions originated from the LLM-assisted parser vs. heuristics so we can tune prompts and know when to fallback.
- **RAG Expansion**: Replace the seed corpus with a larger Recipe1M-derived export, and consider persisting FAISS/Annoy indices so retrieval scales to thousands of recipes.

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
- `src/remy/ocr/llm_client.py`, `src/remy/ocr/parser.py`, `tests/ocr/test_parser.py`: LLM-enhanced receipt parsing and accompanying tests.
- `src/remy/rag/im2recipe.py`, `tests/rag/test_im2recipe.py`: downloaded im2recipe model, hashed retrieval logic, Makefile helper, and unit coverage.

Please keep this handoff file updated with each major change so incoming agents can ramp quickly.
