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
# "Address already in use". `free_port` is a *pre-flight only* self-heal: it frees a
# stale listener left by a PREVIOUS run so we can bind. It is deliberately NOT used on
# our own teardown — for that we kill only the process group we started (below), so we
# never nuke an unrelated process that happens to hold the port or look like a worker.
free_port() {
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" 2>/dev/null || true
  else  # fallback if psmisc/fuser isn't installed: kill the LISTEN pid via ss
    ss -ltnpH "sport = :${PORT}" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | xargs -r kill -9 2>/dev/null || true
  fi
}

# Our own uvicorn process group (set once we launch). setsid makes uvicorn a new
# process-group leader whose PID == PGID, so `kill -"$SERVER_PID"` signals the whole
# group (reloader + its multiprocessing worker) and nothing else.
SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill -TERM "-$SERVER_PID" 2>/dev/null || true
    for _ in 1 2 3 4 5; do            # give the group ~1s to exit gracefully
      kill -0 "$SERVER_PID" 2>/dev/null || break
      sleep 0.2
    done
    kill -KILL "-$SERVER_PID" 2>/dev/null || true   # hard-kill anything left
  fi
}
trap 'cleanup; exit 130' INT TERM
trap cleanup EXIT

free_port                     # pre-flight: clear a stale/orphaned listener so we can bind

# Make sure the optional 'server' deps (fastapi/uvicorn/websockets) are installed.
# Fast no-op when already in sync.
uv sync --extra dev --extra server

echo "→ ygo_engine server: http://localhost:${PORT}  (Ctrl-C to stop)"
# Launch in its own session/process-group (setsid) and keep this shell alive to run
# the traps on shutdown, killing only our group.
setsid uv run uvicorn ygo.server.app:app --port "${PORT}" --reload &
SERVER_PID=$!
wait "$SERVER_PID"
