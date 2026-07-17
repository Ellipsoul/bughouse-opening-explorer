#!/usr/bin/env bash
# Visitor stats for the bughouse explorer, from Caddy's access log via GoAccess.
#
#   site-stats           write a static HTML report to /var/log/caddy/report.html (all history,
#                        including rotated .gz logs)
#   site-stats --live    interactive terminal dashboard (current log only)
#
# View the HTML report by copying it down, e.g.:
#   scp root@<server>:/var/log/caddy/report.html . && xdg-open report.html
#
# The report contains visitor IPs, so it is intentionally NOT served publicly.
set -euo pipefail
CONF=/etc/goaccess-bughouse.conf
REPORT=/var/log/caddy/report.html

if [[ "${1:-}" == "--live" ]]; then
  exec goaccess /var/log/caddy/access.log -p "$CONF"
fi

shopt -s nullglob
LOGS=(/var/log/caddy/access*.log*)   # current log + rotated (gzipped) logs
[[ ${#LOGS[@]} -gt 0 ]] || { echo "no access logs yet"; exit 0; }

# zcat -f transparently reads both plain and gzipped logs; goaccess reads the merged stream.
zcat -f "${LOGS[@]}" | goaccess - -p "$CONF" -o "$REPORT"
echo "wrote $REPORT ($(wc -c < "$REPORT") bytes)"
echo "view it:  scp root@<server>:$REPORT . && xdg-open report.html"
