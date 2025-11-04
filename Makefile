PYTHON ?= python3.11
POETRY ?= $(PYTHON)
PIP ?= $(PYTHON) -m pip
IMAGE_NAME ?= remy
UVICORN ?= uvicorn

.PHONY: install install-dev install-server test lint typecheck format run-server docker-build docker-run clean

install:
	$(PIP) install -e .

install-dev:
	$(PIP) install -e .[dev]

install-server:
	$(PIP) install -e .[server]

test:
	pytest

lint:
	ruff check src tests

typecheck:
	mypy src

format:
	ruff format src tests

run-server:
	$(UVICORN) remy.server.app:app --reload

docker-build:
	docker build -t $(IMAGE_NAME) .

docker-run:
	docker run --rm -p 8000:8000 $(IMAGE_NAME)

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist build
