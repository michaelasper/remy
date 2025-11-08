# Overview

Remy is a multi-agent automation platform—and a nod to Pixar’s rat chef—that orchestrates household dinner planning. It assembles a structured context from inventory, recent meals, preferences, and leftovers before generating candidate menus that respect dietary rules and surface shopping shortfalls.

## Key Capabilities

- Build a rich planning context from SQLite data, pantry leftovers, and household preferences.
- Override diet, allergens, prep time, cuisines, and recipe-search keywords per run.
- Sync DuckDuckGo recipe snippets, im2recipe RAG hits, and llama.cpp/vLLM/Ollama responses into a single prompt.
- Emit observability logs for snippet usage, RAG hits, diet/allergen checks, and shopping shortages.
- Normalize ingredient data, clamp inventory deltas, recompute macros, and expose planner diagnostics in the UI.
- Auto-sync planner shopping shortfalls into the shopping list and nudge users when unchecked items linger.
- Manage inventory, shopping list, preferences, meals, and receipts from one Vue 3 dashboard.

## Agents

| Agent | Role | Inputs | Outputs | Notes |
| --- | --- | --- | --- | --- |
| Context Assembler | Hydrate LLM planning context. | SQLite inventory, meals, preferences, leftovers | `planning_context.json` | Supports per-run overrides + recipe-search options. |
| Menu Planner | Generate candidate meals. | `planning_context.json` | Plan JSON | Rules engine with LLM/RAG augmentation. |
| Diff & Validator | Clamp deltas, compute shortages. | Planner output, inventory | Normalized plan + `shopping_shortfall` | Logs clamps/misses + recomputes macros. |
| Shopping Dispatcher | Push shortfalls downstream. | `shopping_shortfall` | Shopping list entries, HA hooks | Today: auto-syncs to local shopping list DB. |
| Receipt Ingestor | OCR + LLM cleanup. | Uploaded receipts | Inventory suggestions | Logs heuristic vs. LLM suggestions for tuning. |
| Nutrition Estimator | Compute macros per serving. | Candidate ingredients | `macros_per_serving` | Optional extension hook. |
| Notifier | Deliver plans & follow-ups. | Message payloads | Home Assistant notifications / push | Placeholder for automation. |

Future agents: calendar integrator, preference learner, variety scheduler, vision pantry scanner, local LLM evaluator.

## Contracts

```json
PlanningContext {
  "date": "YYYY-MM-DD",
  "prefs": {"diet":"keto","max_time_min":45,"allergens":["peanut"]},
  "recent_meals": [{"date":"2025-11-02","title":"Beef Stir Fry","rating":4}],
  "inventory": [{"id":12,"name":"chicken thigh, boneless","qty":1200,"unit":"g"}],
  "leftovers": [{"name":"beef stew","qty":400,"unit":"g"}],
  "constraints": {"attendees":2,"time_window":"evening","preferred_cuisines":["thai"]},
  "planner_options": {"recipe_search_enabled":true,"recipe_search_keywords":["sheet pan","citrus"]}
}
```

```json
Plan {
  "date": "YYYY-MM-DD",
  "candidates": [
    {
      "title": "Lemon Pepper Chicken Thighs",
      "estimated_time_min": 35,
      "servings": 3,
      "steps": ["Preheat oven to 220°C.","Roast broccoli 18 min.","Cook chicken 14 min."],
      "ingredients_required": [{"ingredient_id":12,"name":"chicken thigh, boneless","qty_g":600}],
      "inventory_deltas": [{"ingredient_id":12,"use_g":600}],
      "shopping_shortfall": [{"name":"lemon pepper","need_g":8,"reason":"not_in_inventory"}],
      "macros_per_serving": {"kcal":520,"protein_g":38,"carb_g":12,"fat_g":34}
    }
  ]
}
```

## Runtime Surfaces & Tooling

- Python 3.11 (`pyproject.toml`), FastAPI backend, Vue 3 SPA front-end.
- CLI entry point: `remy plan context.json --pretty`.
- Endpoints: `/plan`, `/planning-context`, `/inventory*`, `/shopping-list*`, `/receipts*`, `/meals`, `/preferences`, `/metrics`.
- Docker support (`Dockerfile`, `docker-compose.yml`) including llama.cpp sidecar via `llama-cpp-python` on `http://llamacpp:11434/v1`.
- Environment variables: `REMY_DATABASE_PATH`, `REMY_API_TOKEN`, `REMY_LLM_*`, `REMY_RECIPE_SEARCH_*`, `REMY_HOME_ASSISTANT_*`, `REMY_LOG_*`, OCR settings, RAG settings.
- Makefile targets: `install`, `install-dev`, `bootstrap`, `doctor`, `run-server`, `test`, `lint`, `typecheck`, `compose-*`, `llamacpp-setup`, `test-e2e`.

## Operational Notes

- Long-term state lives in SQLite; short-term payloads flow between agents as JSON.
- Guardrails: respect diet/allergen rules, avoid negative inventory, prefer near-expiry items, enforce protein variety.
- KPIs: ≥90 % plan success by 15:10, −15 % waste each month, prep time within prefs, ≥4/5 satisfaction.
- Planner prompts enforce strict JSON schema and token budget (<8k).

## Roadmap

1. **MVP**: mock planner, manual snapshot ingestion, baseline FastAPI + Vue + Docker stack.
2. **Data Wiring**: full SQLite models, approvals, context builder.
3. **Smart Planner**: llama.cpp/vLLM/Ollama/RAG integration (current focus).
4. **Receipt OCR**: landed (Tesseract + LLM clean-up); next is auto-inventory updates.
5. **Automation Enhancements**: notifications, shopping integrations, nutrition scoring, preference learning.

## Contributing

- Keep planner outputs deterministic and schema-valid.
- Use the supplied Make targets for linting/tests.
- Record meaningful entries in `HANDOFF.md`.
- Open pull requests for review; no pushes to `main` without CI passing.
