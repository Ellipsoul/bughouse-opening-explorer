#!/usr/bin/env bash
# Start the bughouse explorer query server.
# Resolves paths relative to this script, so it works from any directory.
set -euo pipefail

# Directory this script lives in (the repo root).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VENV="$DIR/.venv"
SERVE="$VENV/bin/bughouse-explorer-serve"
DB="${1:-$DIR/data/games.db}"   # optional 1st arg overrides the db path

if [[ ! -x "$SERVE" ]]; then
  echo "error: $SERVE not found." >&2
  echo "Set up the venv first:" >&2
  echo "  python3 -m venv '$VENV' && source '$VENV/bin/activate' && pip install -e '$DIR'" >&2
  exit 1
fi

if [[ ! -f "$DB" ]]; then
  echo "error: database not found at $DB" >&2
  echo "Build it with: bughouse-explorer download <username> --db '$DB' && bughouse-explorer index --db '$DB'" >&2
  exit 1
fi

# The server only serves the web UI at / when frontend/dist exists; build it if missing.
FRONTEND="$DIR/frontend"
if [[ ! -d "$FRONTEND/dist" ]]; then
  echo "frontend/dist not found; building the web UI..."
  # node may not be on PATH (e.g. installed under ~/.local/node).
  if ! command -v npm >/dev/null 2>&1 && [[ -x "$HOME/.local/node/bin/npm" ]]; then
    PATH="$HOME/.local/node/bin:$PATH"
  fi
  if ! command -v npm >/dev/null 2>&1; then
    echo "error: npm not found; install Node.js to build the frontend." >&2
    exit 1
  fi
  [[ -d "$FRONTEND/node_modules" ]] || (cd "$FRONTEND" && npm install)
  (cd "$FRONTEND" && npm run build)
fi

echo "Starting server on http://localhost:8000  (db: $DB)"
exec "$SERVE" --db "$DB"
