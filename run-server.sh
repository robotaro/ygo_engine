#!/usr/bin/env bash
#
# Launch the ygo_engine duel server (FastAPI + WebSocket).
#
#   ./run-server.sh [PORT]      # default port 8000
#
# The Python project lives in engine/, so this must run from there — that's the
# whole reason `uv run uvicorn ...` fails from the repo root.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT/engine"
PORT="${1:-8000}"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: 'uv' not found — install it from https://docs.astral.sh/uv/" >&2
  exit 1
fi

# uvicorn --reload forks a worker via multiprocessing. If the reloader is stopped
# abruptly (terminal closed, SIGKILL, a wedged Ctrl-C) that worker can be orphaned —
# re-parented to init/systemd — and keep the socket bound, so the next launch dies with
# "Address already in use". Its command line is `…/python -c from multiprocessing…`, NOT
# "uvicorn", so a naive `pkill -f uvicorn` misses it. `reap` frees the port AND sweeps
# those orphans from this checkout. We run it before starting (self-heal) and on exit.
reap() {
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" 2>/dev/null || true
  else  # fallback if psmisc/fuser isn't installed: kill the LISTEN pid via ss
    ss -ltnpH "sport = :${PORT}" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | xargs -r kill -9 2>/dev/null || true
  fi
  pkill -9 -f "${ROOT}/engine/.venv/bin/python.* -c from multiprocessing" 2>/dev/null || true
}

reap                          # pre-flight: clear a stale/orphaned listener so we can bind
trap 'reap; exit 130' INT TERM
trap reap EXIT                # teardown: never leave a worker holding the port

# Make sure the optional 'server' deps (fastapi/uvicorn/websockets) are installed.
# Fast no-op when already in sync.
uv sync --extra dev --extra server

echo "→ ygo_engine server: http://localhost:${PORT}  (Ctrl-C to stop)"
# Not `exec`: keep this shell alive so the traps above run on shutdown.
uv run uvicorn ygo.server.app:app --port "${PORT}" --reload
