#!/usr/bin/env bash
#
# Launch the ygo_engine web client (Svelte + Vite dev server).
#
#   ./run-client.sh
#
# Vite proxies /api, /ws and /cards to the server on :8000, so start the server
# too (./run-server.sh) — or just use ./dev.sh to run both at once.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/web"

if ! command -v npm >/dev/null 2>&1; then
  echo "error: 'npm' not found — install Node.js from https://nodejs.org/" >&2
  exit 1
fi

# First run on a fresh checkout: pull the frontend dependencies.
[ -d node_modules ] || npm install

echo "→ ygo_engine client (Vite) — open the URL printed below."
exec npm run dev
