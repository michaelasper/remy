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

.PHONY: install install-dev install-server test lint typecheck format run-server docker-build docker-run clean

install:
	$(PIP) install -e .

install-dev:
	$(PIP) install -e .[dev]

install-server:
	$(PIP) install -e .[server]

test:
	$(PYTEST)

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

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist build
