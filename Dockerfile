FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        tesseract-ocr \
        tesseract-ocr-eng \
        poppler-utils \
    && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency metadata first for better caching
COPY pyproject.toml README.md LICENSE /app/

RUN pip install --upgrade pip setuptools wheel

# Install project with server extras
COPY src /app/src
RUN pip install .[server]

# Create a non-root user and prepare writable directories
RUN useradd --create-home --shell /bin/bash remy && \
    mkdir -p /app/data && \
    chown -R remy:remy /app

USER remy

# Expose default server port
EXPOSE 8000

# Default command launches the FastAPI server
CMD ["uvicorn", "remy.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
