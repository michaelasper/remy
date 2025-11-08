# Setup & Configuration

Remy keeps a tiny Pixar-inspired rat chef on call, so the setup below makes sure the “little chef” has the right pantry, OCR knives, and LLM stove to work with.

## Prerequisites

- Python 3.11 (`pyenv install 3.11.9` recommended)
- SQLite (bundled), Git, Make
- Optional: Docker + Docker Compose (for the full stack), VS Code DevContainer support
- OCR extras:
  - Tesseract (`brew install tesseract` or `sudo apt-get install tesseract-ocr`)
  - Poppler utils for PDF rasterization (`brew install poppler` or `sudo apt-get install poppler-utils`)

## Local Installation

```bash
git clone https://github.com/michaelasper/remy.git
cd remy
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
make bootstrap
```

## Running the App

```bash
uvicorn remy.server.app:app --reload
```

- UI: `http://localhost:8000/`
- Planner API: `POST /plan` (requires `Authorization: Bearer $REMY_API_TOKEN` if set)
- Metrics: `GET /metrics`

Use the CLI to inspect plans without the UI:

```bash
remy plan path/to/context.json --pretty
```

## LLM & RAG Support

- `make llamacpp-setup` downloads the default Qwen2.5 0.5B Instruct GGUF and starts a llama.cpp sidecar at `http://llamacpp:11434/v1`.
- Configure alternative runtimes via:
  - `REMY_LLM_PROVIDER` (`openai`, `ollama`)
  - `REMY_LLM_BASE_URL`
  - `REMY_LLM_MODEL`, `REMY_LLM_TEMPERATURE`, `REMY_LLM_MAX_TOKENS`
- DuckDuckGo search snippets: `REMY_RECIPE_SEARCH_ENABLED=1`, optional `REMY_RECIPE_SEARCH_RESULTS`.
- RAG settings:
  - `REMY_RAG_ENABLED`
  - `REMY_RAG_MODEL_PATH`, `REMY_RAG_CORPUS_PATH`, `REMY_RAG_INDEX_PATH`
  - `REMY_RAG_TOP_K`, `REMY_RAG_EMBEDDING_DIM`, `REMY_RAG_INDEX_TREES`

## OCR Pipeline

- Archive path: `REMY_OCR_ARCHIVE_PATH` (default `./data/receipts_archive`)
- Worker toggles:
  - `REMY_OCR_WORKER_ENABLED`
  - `REMY_OCR_WORKER_POLL_INTERVAL`
  - `REMY_OCR_WORKER_BATCH_SIZE`
- LLM-assisted parsing: set `REMY_RECEIPT_LLM_ENABLED=1` and configure `REMY_RECEIPT_LLM_*` (provider/base/model/temperature/max tokens).
- CLI helpers:
  - `remy receipt-ocr <id>` or `make ocr OCR_RECEIPT_ID=<id>`
  - `make ocr-worker ARGS="--poll-interval 2 --batch-size 3"`

## Docker / Compose

```bash
docker compose up --build -d
# or
docker build -t remy . && docker run -p 8000:8000 remy
```

- Compose spins up FastAPI, the Vue front-end, SQLite volume, and llama.cpp sidecar (`service: llamacpp`).
- Data volume: `remy-data` mounted at `/app/data`.

## Make Targets

| Target | Description |
| --- | --- |
| `make install`, `install-dev`, `install-server` | Install project extras |
| `bootstrap` | Set up `.venv` + tooling |
| `doctor` | Environment sanity checks |
| `run-server` (`DURATION=5` optional) | Run FastAPI |
| `test`, `lint`, `typecheck`, `format`, `coverage` | Quality gates |
| `docker-build`, `docker-run`, `compose-up`/`down`/`logs` | Container workflows |
| `llamacpp-setup` | Download + launch llama.cpp sidecar |
| `test-e2e` | Compose-based end-to-end test (`RUN_E2E=1`) |

## Environment Reference

- Core: `REMY_DATABASE_PATH`, `REMY_API_TOKEN`, `REMY_LOG_LEVEL`, `REMY_LOG_FORMAT`, `REMY_LOG_REQUESTS`
- Integrations: `REMY_HOME_ASSISTANT_BASE_URL`, `REMY_HOME_ASSISTANT_TOKEN`
- Planner toggles: `REMY_RECIPE_SEARCH_*`, `REMY_RAG_*`, `REMY_LLM_*`
- OCR/Receipt toggles: `REMY_OCR_*`, `REMY_RECEIPT_LLM_*`

Store secrets in `.env` (ignored) and never commit them. Log redaction is enabled for API/Home Assistant tokens.
