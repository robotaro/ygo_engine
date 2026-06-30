#!/usr/bin/env bash
#
# Launch BOTH the server (background) and the web client (foreground) for local
# development. Ctrl-C stops the client and tears the server down with it.
#
#   ./dev.sh [SERVER_PORT]      # default 8000
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-8000}"

# Always clean up the server when this script exits (Ctrl-C, error, or normal).
cleanup() { pkill -f "uvicorn ygo.server.app" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "Starting server on :${PORT} …"
"$ROOT/run-server.sh" "$PORT" &

# The client runs in the foreground until you stop it (Ctrl-C).
"$ROOT/run-client.sh"
