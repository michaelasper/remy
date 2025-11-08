AGENTS.md — Jarvis Dinner Planner (Remy)

Purpose: Keep a living map of the multi-agent architecture, runtime surfaces, and success metrics so contributors (human or automated) can ship changes confidently.

⸻

🎯 High-Level Goal

Create a daily dinner-planning automation that:
	•	Uses available inventory and recent meals to propose balanced options.
	•	Adapts to constraints (time, diet, preferences, events).
	•	Generates 2–3 candidates with recipe steps, macros, and a shopping delta.
	•	Notifies the household automatically at 3:00 PM, and updates inventory upon approval.

⸻

🧩 Agents Overview

| Agent | Purpose | Inputs | Outputs | Notes |
| --- | --- | --- | --- | --- |
| Context Assembler | Build LLM planning context from DB + external signals. | SQLite / JSON snapshots, preferences, leftovers | `planning_context.json` | Hydrates from SQLite (inventory, meals, prefs, leftovers) and honors per-run diet/allergen/cuisine overrides; next lift is external cues (calendar/weather). |
| Menu Planner | Generate candidate meals. | `planning_context.json` | Plan JSON | Stub delegates to `planner.generate_plan()`; replace with rules/LLM. |
| Diff & Validator | Canonicalize ingredients, compute shortages. | Planner output, inventory | Normalized plan + `shopping_shortfall` | Expands unit conversions, recomputes macros, clamps deltas, and emits diagnostics for the UI/logs. |
| Approvals Orchestrator | Handle human approval, dispatch updates. | Normalized plan | Meal + inventory mutations | To be built once DB writes exist. |
| Shopping Dispatcher | Push shortages to shopping services. | `shopping_shortfall` | HA API calls, future vendor carts | Planner now auto-sends shortfalls to the shopping list DB; future work is external carts/HA sync. |
| Receipt Ingestor | Parse receipts/OCR -> inventory updates. | Images/CSV/email, `/receipts` uploads | Inventory upserts | Stores uploads in SQLite, drives the Tesseract OCR pipeline, and now supports operator approval to ingest parsed line items into inventory. |
| Nutrition Estimator | Compute macros per serving. | Candidate ingredients | `macros_per_serving` | Optional extension. |
| Notifier | Deliver plan + follow-ups to humans. | Message payloads | Home Assistant notifications / push | Stubbed.

Future agents: Calendar Integrator, Preference Learner, Variety Scheduler, Vision Pantry Scanner, Local LLM evaluator.

⸻

🧠 Shared Contracts

Planning Context

{
  "date": "YYYY-MM-DD",
  "prefs": {"diet":"keto","max_time_min":45},
  "recent_meals": [{"date":"2025-11-02","title":"Beef Stir Fry","rating":4}],
  "inventory": [
    {"id":12,"name":"chicken thigh, boneless","qty":1200,"unit":"g","best_before":"2025-11-10"},
    {"id":33,"name":"broccoli","qty":800,"unit":"g","best_before":"2025-11-06"}
  ],
  "leftovers": [{"name":"beef stew","qty":400,"unit":"g","best_before":"2025-11-04"}],
  "constraints": {"attendees":2,"time_window":"evening","preferred_cuisines":["thai"]},
  "planner_options": {"recipe_search_enabled":true,"recipe_search_keywords":["sheet pan","citrus"]}
}

Plan (normalized output)

{
  "date": "YYYY-MM-DD",
  "candidates": [
    {
      "title": "Lemon Pepper Chicken Thighs",
      "estimated_time_min": 35,
      "servings": 3,
      "steps": ["Preheat oven to 220°C.","Roast broccoli 18 min.","Cook chicken 14 min."],
      "ingredients_required": [
        {"ingredient_id":12,"name":"chicken thigh, boneless","qty_g":600},
        {"ingredient_id":33,"name":"broccoli","qty_g":500}
      ],
      "inventory_deltas": [
        {"ingredient_id":12,"use_g":600},
        {"ingredient_id":33,"use_g":500}
      ],
      "shopping_shortfall": [{"ingredient_id":77,"name":"lemon pepper","need_g":8,"reason":"out of stock"}],
      "macros_per_serving": {"kcal":520,"protein_g":38,"carb_g":12,"fat_g":34}
    }
  ]
}


⸻

⚙️ Runtime Surfaces & Tooling

- Python 3.11 (pyenv `.python-version` or `.venv`), project metadata in `pyproject.toml`.
- CLI entry point: `remy plan path/to/context.json --pretty`.
- FastAPI server (`remy.server.app:app`) with endpoints:
  - `POST /plan` — generate candidates.
  - `GET /inventory` — list current inventory snapshot.
  - `POST /receipts`, `GET /receipts`, `GET /receipts/{id}/download` — upload and retrieve receipt files for OCR.
- Web UI served at `/` — Vue 3 SPA (planner, inventory, preferences, receipts).
- Docker:
  - `Dockerfile` builds non-root image with persisted `/app/data`.
  - `docker-compose.yml` exposes API on `:8000` and mounts `remy-data` volume.
- Native LLM runtime: Docker Compose now launches a llama.cpp sidecar (`llama-cpp-python` server) on `http://llamacpp:11434/v1`; run `make llamacpp-setup` (or `docker compose up -d llamacpp`) to start it and download the default Qwen2.5 0.5B Instruct GGUF. Remy injects `REMY_LLM_PROVIDER=openai`, `REMY_LLM_BASE_URL`, and `REMY_LLM_MODEL` so the planner talks to the sidecar automatically. Switch `REMY_LLM_PROVIDER`/`REMY_LLM_BASE_URL` if you prefer Ollama, vLLM, or another OpenAI-compatible runtime, and flip `REMY_RECIPE_SEARCH_ENABLED=1` to feed the planner DuckDuckGo recipe snippets.
- Makefile targets:
  - `install`, `install-dev`, `install-server`, `test`, `lint`, `typecheck`, `format`.
  - `bootstrap`, `doctor`, `run-server` (optionally `DURATION=5`), `docker-build`, `docker-run`.
  - `compose-up/down/logs`, `test-e2e` (requires Docker daemon).
- Dev Container support (`.devcontainer/`) for VS Code / `devcontainer up`.
- Settings via environment: `REMY_DATABASE_PATH`, `REMY_HOME_ASSISTANT_*`, `REMY_API_TOKEN`, `REMY_LOG_LEVEL`, `REMY_LOG_FORMAT`, `REMY_LOG_REQUESTS`.

⸻

🔁 Daily Task Graph (Target State)
1. **Context Assembler** pulls inventory (DB/snapshot), preferences, leftovers, calendar cues.
2. **Menu Planner** (rules/LLM) emits up to 3 candidate dinners.
3. **Diff & Validator** normalizes ingredients, calculates shortages, enforces schema.
4. **Approvals Orchestrator** notifies household, accepts approval/decline.
5. On approval, update inventory + push shopping deltas via **Shopping Dispatcher**.

Fallback: resend most recent approved plan if planner or approval flow fails.

⸻

🧮 Memory and State
	•	Long-term: SQLite for all persistent data.
	•	Short-term: JSON payloads passed between agents.
	•	Consistency: Deterministic outputs; schema-validated at each step.

⸻

🔒 Constraints and Safety
	•	Respect dietary preferences; avoid allergens (future: pref.allergens).
	•	Prevent negative inventory or duplicate deductions.
	•	Favor near-expiry ingredients.
	•	Avoid repeating the same protein within 3 days.

⸻

📊 KPIs / Success Criteria

Metric	Target	Description
Plan success rate	≥ 90 %	Days with valid plan by 3:10 PM
Waste reduction	− 15 % / month	Ingredients expiring unused
Median prep time	≤ pref.max_time_min	Weekday dinners
Avg satisfaction	≥ 4 / 5	Based on ratings


⸻

🧠 Planner Prompts

System Prompt

You are a household dinner planner. Optimize for (1) using inventory before expiry, (2) low weekday prep time, (3) variety, and (4) preferences. Output STRICT JSON per schema. Use grams/ml/count.

User Prompt

Here is the planning context for DATE: <context-json>\nReturn 2–3 candidate meals.

Guardrails
	•	If data incomplete → empty candidates.
	•	Never invent unavailable ingredients.
	•	Maintain total token count < 8 k.

⸻

🧪 Testing Strategy

- **Unit**: planner scaffolds, future diff/normalization logic.
- **Schema**: Pydantic validation for `PlanningContext` & `Plan`.
- **Integration**:
  - FastAPI endpoints via `TestClient` (`tests/integration/`).
  - Inventory API/HTML view + plan endpoint coverage.
- **End-to-end**: `tests/e2e/test_compose_plan.py` spins up Docker Compose stack (opt-in with `RUN_E2E=1`).
- **Snapshot**: TODO once real planner output exists.

⸻

🚀 Rollout Phases
1. **MVP (current)**: mock planner, inventory snapshot, FastAPI + web UI, Docker Compose baseline.
2. **Data Wiring**: real SQLite schema, Context Assembler reading/writing DB, Approvals flow.
3. **Smart Planner**: integrate llama.cpp/vLLM/Ollama + recipe corpus (RAG).
4. **Receipt OCR**: (MVP landed) local Tesseract pipeline + UI preview; next step is auto-inventory updates.
5. **Automation Enhancements**: Notifications, shopping integrations, nutrition scoring, preference learning.

⸻

🔐 Security & Privacy
	•	All data stored locally; no cloud sync by default.
	•	API tokens kept in .env, not checked into source control.
	•	Logging redacts API/Home Assistant tokens and adds `X-Request-ID` correlation per request.
	•	If remote LLM used, redact household-specific identifiers.

⸻

❓ Open Questions
	•	Calendar integration for time-based filtering?
	•	Automated leftovers decay model?
	•	Instacart/Amazon API integration vs. HA shopping list only?

⸻

Implementation Hooks
- Replace `src/remy/planner/app/planner.py::generate_plan` placeholder with real logic (rules → LLM).
- Implement SQLite models/repositories (inventory, meals, preferences) and connect Context Assembler.
- Build Approvals flow + `/plan/approve` endpoint, update Notifier + Shopping Dispatcher.
- Extend the OCR pipeline (`ReceiptOcrService`) to map extracted text into structured inventory deltas.
- Add heuristics/rules on top of the OCR worker to route parsed items into the inventory repository safely.
- Iterate on the receipt parser’s heuristics/ML so quantities, prices, and inventory mappings become production-grade.
- Harden Docker stack (health checks, production env overrides) and expand e2e coverage.
