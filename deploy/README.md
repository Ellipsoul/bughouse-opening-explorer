# Deployment

The explorer runs as a systemd service behind Caddy (which terminates HTTPS via Let's Encrypt).
Routine deploys are one command; the files here are the server-side configuration, kept in the repo
so a server can be rebuilt from scratch.

## Routine deploy

From the repo root:

```sh
./deploy.sh                              # build frontend, sync code, restart service
BUGHOUSE_SERVER=root@1.2.3.4 ./deploy.sh # target a different server
```

This deploys **code only**. The database is managed separately (see below).

## First-time server setup

On a fresh Ubuntu/Fedora server (examples use Fedora `dnf`):

1. **Packages & user**
   ```sh
   dnf -y install rsync caddy firewalld python3 python3-pip
   systemctl enable --now firewalld
   firewall-cmd --permanent --add-service=http --add-service=https && firewall-cmd --reload
   useradd --system --create-home --home-dir /opt/bughouse --shell /usr/sbin/nologin bughouse
   ```

2. **App code & virtualenv**
   ```sh
   mkdir -p /opt/bughouse/app /opt/bughouse/data
   # sync the repo to /opt/bughouse/app (deploy.sh does this for code; for the first push,
   # rsync the whole repo excluding data/, .venv/, node_modules/, frontend/dist is built on deploy)
   python3 -m venv /opt/bughouse/venv
   /opt/bughouse/venv/bin/pip install -e /opt/bughouse/app
   chown -R bughouse:bughouse /opt/bughouse
   ```

3. **Service & reverse proxy**
   ```sh
   cp deploy/bughouse.service /etc/systemd/system/
   systemctl daemon-reload && systemctl enable --now bughouse
   cp deploy/Caddyfile /etc/caddy/Caddyfile   # edit the domain first
   systemctl enable --now caddy
   ```

4. **DNS** — point an A record (and AAAA for IPv6) at the server; Caddy obtains the TLS
   certificate automatically once the domain resolves.

## The database

`data/games.db` is **not** in the repo (it's gigabytes and regenerable). Options:

- **Build on the server:** `bughouse-explorer download <user> --db /opt/bughouse/data/games.db`
  then `bughouse-explorer index --db /opt/bughouse/data/games.db`. Indexing also builds the
  `move_agg` summary table that keeps the default view fast.
- **Upload a local copy:** checkpoint the WAL, then
  `rsync -a --partial --inplace data/games.db root@SERVER:/opt/bughouse/data/` and
  `chown bughouse:bughouse` it. Restart the service afterward.

After replacing the database, `systemctl restart bughouse` to clear the in-process query caches.

## Visitor stats

Caddy writes a durable JSON access log to `/var/log/caddy/access.log` (rotated by Caddy itself,
~1 year retained). The `log` block in `Caddyfile` strips the variable-order `headers`/`tls`/
`resp_headers` fields so the log is a stable shape GoAccess can parse. GoAccess config lives at
`deploy/goaccess.conf` → `/etc/goaccess-bughouse.conf`.

View stats with the `site-stats` helper (`deploy/site-stats.sh` → `/usr/local/bin/site-stats`):

```sh
site-stats          # write /var/log/caddy/report.html (all history, incl. rotated logs)
site-stats --live   # interactive terminal dashboard (current log)
```

The report contains visitor IPs, so it is not served publicly. Copy it down to view:

```sh
scp root@<server>:/var/log/caddy/report.html . && xdg-open report.html
```

