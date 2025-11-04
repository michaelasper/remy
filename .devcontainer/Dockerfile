FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends build-essential git && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE /workspace/
COPY src /workspace/src
COPY tests /workspace/tests
COPY AGENTS.md /workspace/AGENTS.md

RUN pip install --upgrade pip setuptools wheel && \
    pip install -e .[dev,server]

CMD ["bash"]
