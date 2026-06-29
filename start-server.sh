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

echo "Starting server on http://localhost:8000  (db: $DB)"
exec "$SERVE" --db "$DB"
