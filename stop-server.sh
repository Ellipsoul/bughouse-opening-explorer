#!/usr/bin/env bash
# Stop the bughouse explorer query server.
# Finds whatever process is listening on the server port and terminates it.
set -euo pipefail

PORT="${1:-8000}"   # optional 1st arg overrides the port (matches start-server.sh default)

# Collect listening PIDs for the port. Prefer lsof; fall back to ss/fuser.
pids=""
if command -v lsof >/dev/null 2>&1; then
  pids="$(lsof -t -i "TCP:$PORT" -s TCP:LISTEN 2>/dev/null || true)"
elif command -v ss >/dev/null 2>&1; then
  pids="$(ss -ltnpH "sport = :$PORT" 2>/dev/null \
            | grep -oP 'pid=\K[0-9]+' | sort -u || true)"
elif command -v fuser >/dev/null 2>&1; then
  pids="$(fuser "$PORT/tcp" 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true)"
else
  echo "error: need one of lsof, ss, or fuser to find the server process." >&2
  exit 1
fi

if [[ -z "$pids" ]]; then
  echo "No server listening on port $PORT."
  exit 0
fi

echo "Stopping server on port $PORT (PID(s): $(echo "$pids" | tr '\n' ' '))"

# Ask politely first.
kill $pids 2>/dev/null || true

# Give it up to ~5s to exit, then force-kill anything still alive.
for _ in 1 2 3 4 5 6 7 8 9 10; do
  alive=""
  for pid in $pids; do
    kill -0 "$pid" 2>/dev/null && alive="$alive $pid"
  done
  [[ -z "$alive" ]] && { echo "Server stopped."; exit 0; }
  sleep 0.5
done

echo "Server did not exit gracefully; forcing (SIGKILL)." >&2
kill -9 $alive 2>/dev/null || true
echo "Server stopped."
