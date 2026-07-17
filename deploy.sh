#!/usr/bin/env bash
# Deploy the bughouse explorer to the production server: build the frontend, sync the app code and
# built assets, then restart the service. Run from anywhere; paths resolve to this repo.
#
#   ./deploy.sh                 # deploy to the default server
#   BUGHOUSE_SERVER=root@1.2.3.4 ./deploy.sh   # deploy elsewhere (e.g. a US box)
#
# This deploys CODE only. The database lives on the server and is refreshed separately (a full
# `bughouse-explorer index` run also rebuilds the move_agg summary table). First-time server setup
# is documented in deploy/README.md.
set -euo pipefail

SERVER="${BUGHOUSE_SERVER:-root@138.199.195.186}"
APP_DIR="/opt/bughouse/app"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Building frontend"
# node may be installed under ~/.local/node rather than on PATH.
if ! command -v npm >/dev/null 2>&1 && [[ -x "$HOME/.local/node/bin/npm" ]]; then
  export PATH="$HOME/.local/node/bin:$PATH"
fi
( cd "$REPO/frontend" && npm run build )

echo "==> Syncing backend package to $SERVER"
rsync -a --delete --exclude='__pycache__' \
  "$REPO/bughouse_explorer/" "$SERVER:$APP_DIR/bughouse_explorer/"

echo "==> Syncing built frontend to $SERVER"
rsync -a --delete "$REPO/frontend/dist/" "$SERVER:$APP_DIR/frontend/dist/"

echo "==> Fixing ownership and restarting service"
ssh "$SERVER" '
  chown -R bughouse:bughouse /opt/bughouse/app &&
  systemctl restart bughouse &&
  sleep 2 &&
  systemctl is-active bughouse
'

echo "==> Deployed. https://explorer.josephw.me"
