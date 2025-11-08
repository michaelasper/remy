# Testing Strategy

Remy ships with a layered test suite so the rat chef never serves undercooked code. Run everything with `pytest` or targeted subsets via `make test`.

## Unit Tests

- Validate planner utilities (diff/normalization, macro recomputation, heuristics).
- Exercise receipt parsing and OCR helpers (`tests/ocr/`).
- Cover repository helpers and agents in isolation.

## Schema / Contract Tests

- Ensure `PlanningContext`, `Plan`, and related models accept/deny the expected payloads.
- Use `Plan.model_validate_json` and pydantic aliases to guarantee field names stay stable.

## Integration Tests

- FastAPI `TestClient` exercises `/plan`, `/planning-context`, `/inventory*`, `/shopping-list*`, `/receipts*`, `/meals`, and `/preferences`.
- Shopping-list tests verify add/update/delete flows plus add-to-inventory transitions.
- Security tests confirm `REMY_API_TOKEN` gates mutating endpoints.

## End-to-End

- `tests/e2e/test_compose_plan.py` spins up the Docker Compose stack (set `RUN_E2E=1`) to verify the planner endpoint with real services (llama.cpp, SQLite volume).

## Snapshot / Determinism

- Planner outputs should stay deterministic for fixed contexts; add snapshots as the real planner stabilizes.

## Helpful Commands

```bash
pytest                                  # full suite
pytest tests/integration/test_plan_endpoint.py
make lint format typecheck              # quality gates
make test-e2e RUN_E2E=1                 # compose-based e2e
```

Always run `pytest` (and relevant Make targets) before opening a pull request.
