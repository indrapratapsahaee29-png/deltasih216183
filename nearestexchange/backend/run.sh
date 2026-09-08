#!/usr/bin/env bash
# One-command setup + run. Creates a venv so pip never hits
# "externally-managed-environment" on modern macOS/Linux.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but was not found on PATH." >&2
  exit 1
fi

if [ ! -d venv ]; then
  echo "Creating virtualenv..."
  python3 -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt
echo "NearestExchange listening on ${HOST}:${PORT}"
exec python -m uvicorn main:app --host "$HOST" --port "$PORT"
