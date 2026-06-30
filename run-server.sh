#!/usr/bin/env bash
#
# Launch the ygo_engine duel server (FastAPI + WebSocket).
#
#   ./run-server.sh [PORT]      # default port 8000
#
# The Python project lives in engine/, so this must run from there — that's the
# whole reason `uv run uvicorn ...` fails from the repo root.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/engine"
PORT="${1:-8000}"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: 'uv' not found — install it from https://docs.astral.sh/uv/" >&2
  exit 1
fi

# Make sure the optional 'server' deps (fastapi/uvicorn/websockets) are installed.
# Fast no-op when already in sync.
uv sync --extra dev --extra server

echo "→ ygo_engine server: http://localhost:${PORT}  (Ctrl-C to stop)"
exec uv run uvicorn ygo.server.app:app --port "${PORT}" --reload
