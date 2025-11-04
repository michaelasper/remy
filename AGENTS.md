AGENTS.md — Jarvis Dinner Planner

Purpose: Define the multi-agent architecture and goals so Codex (and future contributors) can reason about the system’s structure, context, and success metrics.

⸻

🎯 High-Level Goal

Create a daily dinner-planning automation that:
	•	Uses available inventory and recent meals to propose balanced options.
	•	Adapts to constraints (time, diet, preferences, events).
	•	Generates 2–3 candidates with recipe steps, macros, and a shopping delta.
	•	Notifies the household automatically at 3:00 PM, and updates inventory upon approval.

⸻

🧩 Agents Overview

Agent	Purpose	Inputs	Outputs	Notes
Context Assembler	Builds LLM planning context from DB and external sources.	SQLite data, preferences, leftovers.	planning_context.json	Prepares all structured data for the planner.
Menu Planner	LLM or rules engine generating candidate meals.	planning_context.json	Plan (JSON)	Uses planner.generate_plan(); initially mock, later local LLM.
Diff & Validator	Canonicalizes ingredient names, computes shortages, validates JSON.	Planner output, inventory DB.	Normalized plan + shopping_shortfall.	Ensures schema compliance.
Approvals Orchestrator	Handles human approval, DB updates, notifications.	Normalized plan.	Meal + inventory mutations.	Transactional changes.
Shopping Dispatcher	Sends grocery needs to Home Assistant list or vendor cart.	Shortfall list.	HA API calls.	Future: Instacart, Amazon, etc.
Receipt Ingestor	Parses CSV/email/OCR receipts to update inventory.	Raw receipt data.	Inventory upserts.	Enables passive updates.
Nutrition Estimator	Calculates macros using per-ingredient nutrition table.	Ingredient quantities.	macros_per_serving	Optional extension.
Notifier	Communicates plans and updates to users.	Message payloads.	HA notification or push.	Ensures timely alerts.

Future agents: Calendar Integrator, Preference Learner, Variety Scheduler, Vision Pantry Scanner.

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
  "constraints": {"attendees":2,"time_window":"evening"}
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

⚙️ Tools and APIs
	•	Database: SQLite tables (inventory, meals, prefs, ingredients).
	•	LLM Runtime: generate_plan(context_json) (Ollama/vLLM once available).
	•	Home Assistant:
	•	Notifications → /api/services/persistent_notification/create
	•	Shopping list → /api/shopping_list/item
	•	Scheduler: APScheduler @ 15:00 local time.
	•	Web UI: /plan/today viewer and future /plan/approve endpoint.

⸻

🔁 Daily Task Graph
	1.	Context Assembler builds context JSON.
	2.	Menu Planner returns a plan.
	3.	Diff & Validator normalizes + computes shortages.
	4.	Approvals Orchestrator posts summary via Notifier.
	5.	On approval → update DB + dispatch shopping items.

Fallback: reuse last approved meal if planner fails.

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
	•	Unit: inventory diffing, normalization, approval mutations.
	•	Schema: JSON validation vs. models.Plan.
	•	Integration: HA API mock tests.
	•	Snapshot: fixed mock context → deterministic plan output.

⸻

🚀 Rollout Phases
	1.	MVP: mock planner, manual CSV imports, HA notifications.
	2.	LLM Integration: connect to Ollama/vLLM.
	3.	RAG Recipe Corpus: embed 100–300 local recipes.
	4.	Receipt OCR/email ingestion.
	5.	Nutrition scoring and variety tracking.

⸻

🔐 Security & Privacy
	•	All data stored locally; no cloud sync by default.
	•	API tokens kept in .env, not checked into source control.
	•	If remote LLM used, redact household-specific identifiers.

⸻

❓ Open Questions
	•	Calendar integration for time-based filtering?
	•	Automated leftovers decay model?
	•	Instacart/Amazon API integration vs. HA shopping list only?

⸻

Implementation Hook: Start with planner/app/planner.py::generate_plan(); ensure models.Plan validation passes. Next milestone → /plan/approve endpoint to persist approvals.
