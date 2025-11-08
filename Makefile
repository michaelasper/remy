PYTHON ?= python3
ifeq ($(origin PYTHON), default)
ifneq ($(wildcard .venv/bin/python),)
PYTHON := .venv/bin/python
endif
ifneq ($(wildcard .venv/Scripts/python.exe),)
PYTHON := .venv/Scripts/python.exe
endif
endif
POETRY ?= $(PYTHON)
PIP ?= $(PYTHON) -m pip
IMAGE_NAME ?= remy
UVICORN ?= $(PYTHON) -m uvicorn
PYTEST ?= $(PYTHON) -m pytest
RUFF ?= $(PYTHON) -m ruff
MYPY ?= $(PYTHON) -m mypy
DOCKER ?= docker
HOST ?= 127.0.0.1
PORT ?= 8000
DURATION ?=
COMPOSE ?= docker-compose
DEVTOOLS ?= $(PYTHON) -m remy.devtools
LLAMACPP_SERVICE ?= llamacpp

.PHONY: install install-dev install-server test test-e2e lint typecheck format run-server docker-build docker-run compose-up compose-down compose-logs check coverage clean bootstrap doctor ocr ocr-worker llamacpp-setup

install:
	$(PIP) install -e .

install-dev:
	$(PIP) install -e .[dev]

install-server:
	$(PIP) install -e .[server]

test:
	$(PYTEST)

test-e2e:
	RUN_E2E=1 $(PYTHON) -m pytest tests/e2e

check:
	$(MAKE) doctor
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) test

coverage:
	$(PYTEST) --cov=src/remy --cov-report=term-missing

lint:
	$(RUFF) check src tests

typecheck:
	$(MYPY) src

format:
	$(RUFF) format src tests

run-server:
	REMY_SERVER_HOST=$(HOST) \
	REMY_SERVER_PORT=$(PORT) \
	REMY_SERVER_DURATION=$(DURATION) \
	RELOAD=$(RELOAD) \
	$(PYTHON) -m remy.server.run

docker-build:
	@if ! command -v $(DOCKER) >/dev/null 2>&1; then \
		echo "Docker command not found. Install Docker or set DOCKER to an alternative."; \
		exit 1; \
	fi
	$(DOCKER) build -t $(IMAGE_NAME) .

docker-run:
	@if ! command -v $(DOCKER) >/dev/null 2>&1; then \
		echo "Docker command not found. Install Docker or set DOCKER to an alternative."; \
		exit 1; \
	fi
	$(DOCKER) run --rm -p 8000:8000 $(IMAGE_NAME)

.PHONY: compose-up compose-down compose-logs

compose-up:
	@if command -v $(firstword $(COMPOSE)) >/dev/null 2>&1; then \
		$(COMPOSE) up -d --build; \
	elif command -v $(DOCKER) >/dev/null 2>&1; then \
		$(DOCKER) compose up -d --build; \
	else \
		echo "Docker Compose not found. Install docker-compose or set COMPOSE to an alternative."; \
		exit 1; \
	fi

compose-down:
	@if command -v $(firstword $(COMPOSE)) >/dev/null 2>&1; then \
		$(COMPOSE) down --remove-orphans; \
	elif command -v $(DOCKER) >/dev/null 2>&1; then \
		$(DOCKER) compose down --remove-orphans; \
	else \
		echo "Docker Compose not found. Install docker-compose or set COMPOSE to an alternative."; \
		exit 1; \
	fi

compose-logs:
	@if command -v $(firstword $(COMPOSE)) >/dev/null 2>&1; then \
		$(COMPOSE) logs -f; \
	elif command -v $(DOCKER) >/dev/null 2>&1; then \
		$(DOCKER) compose logs -f; \
	else \
		echo "Docker Compose not found. Install docker-compose or set COMPOSE to an alternative."; \
		exit 1; \
	fi

bootstrap:
	$(DEVTOOLS) bootstrap

doctor:
	$(DEVTOOLS) doctor

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist build

OCR_RECEIPT_ID ?=
OCR_LANG ?= eng

ocr:
	@if [ -z "$(OCR_RECEIPT_ID)" ]; then \
		echo "Set OCR_RECEIPT_ID=<receipt-id> to run OCR on a stored receipt."; \
		exit 1; \
	fi
	$(PYTHON) -m remy.cli receipt-ocr $(OCR_RECEIPT_ID) --lang $(OCR_LANG)

ocr-worker:
	$(PYTHON) -m remy.cli ocr-worker $(ARGS)

llamacpp-setup:
	@if ! command -v $(DOCKER) >/dev/null 2>&1; then \
		echo "Docker command not found. Install Docker or set DOCKER to an alternative."; \
		exit 1; \
	fi
	@if command -v $(firstword $(COMPOSE)) >/dev/null 2>&1; then \
		$(COMPOSE) up -d $(LLAMACPP_SERVICE); \
	else \
		$(DOCKER) compose up -d $(LLAMACPP_SERVICE); \
	fi
	@echo "llama.cpp service is starting in Docker Compose (model download handled by the container entrypoint)."
