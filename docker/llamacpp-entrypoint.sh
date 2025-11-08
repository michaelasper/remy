#!/bin/sh
set -eu

MODEL_PATH="${LLAMACPP_MODEL_PATH:-/models/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf}"
MODEL_URL="${LLAMACPP_MODEL_URL:-}"
CONTEXT_SIZE="${LLAMACPP_CONTEXT_SIZE:-4096}"
export MODEL_PATH MODEL_URL

if [ ! -f "$MODEL_PATH" ]; then
  if [ -z "$MODEL_URL" ]; then
    echo "LLAMACPP_MODEL_URL must be set to download the GGUF checkpoint." >&2
    exit 1
  fi
  MODEL_PATH="$MODEL_PATH" MODEL_URL="$MODEL_URL" python - <<'PY'
import os
import urllib.request

model_path = os.environ["MODEL_PATH"]
model_url = os.environ["MODEL_URL"]
os.makedirs(os.path.dirname(model_path), exist_ok=True)
print(f"Downloading {model_url} -> {model_path}", flush=True)
urllib.request.urlretrieve(model_url, model_path)
PY
fi

exec /app/llama-server \
  -m "$MODEL_PATH" \
  -c "$CONTEXT_SIZE" \
  --port 11434 \
  --host 0.0.0.0
