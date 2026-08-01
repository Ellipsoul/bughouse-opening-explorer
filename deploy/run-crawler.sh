#!/bin/sh
set -eu

if [ -n "${BUGHOUSE_RUN_ID:-}" ]; then
    exec /opt/bughouse/venv/bin/bughouse-explorer crawl resume "$BUGHOUSE_RUN_ID"
fi

exec /opt/bughouse/venv/bin/bughouse-explorer crawl bootstrap
