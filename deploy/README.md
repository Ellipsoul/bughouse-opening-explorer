# Deployment

The explorer runs as a systemd service behind Caddy (which terminates HTTPS via Let's Encrypt).
Routine deploys are one command; the files here are the server-side configuration, kept in the repo
so a server can be rebuilt from scratch.

The crawler is separate from the legacy web service. It uses local SQLite, has no network-facing
database or Docker dependency, and runs as a dedicated `bughouse-crawler` user.

## Crawler setup

Install `sqlite` and `util-linux` (for `flock`), then create the least-privilege account and its
protected environment file:

```sh
dnf -y install sqlite util-linux
useradd --system --no-create-home --home-dir /opt/bughouse --shell /usr/sbin/nologin bughouse-crawler
install -d -o bughouse-crawler -g bughouse-crawler -m 0750 /opt/bughouse/data
install -d -o root -g bughouse-crawler -m 0750 /etc/bughouse
install -o root -g bughouse-crawler -m 0640 deploy/crawler.env.example /etc/bughouse/crawler.env
# Edit CHESSCOM_USER_AGENT in /etc/bughouse/crawler.env to include real contact information.
```

Install/migrate the application and start the initial crawl manually:

```sh
/opt/bughouse/venv/bin/pip install -e /opt/bughouse/app
sudo -u bughouse-crawler /opt/bughouse/venv/bin/bughouse-explorer \
  crawl --crawler-db /opt/bughouse/data/crawler.db migrate
cp deploy/bughouse-crawler.service /etc/systemd/system/
cp deploy/bughouse-crawler-monthly.service /etc/systemd/system/
cp deploy/bughouse-crawler-monthly.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start bughouse-crawler.service
systemctl enable --now bughouse-crawler-monthly.timer
```

The bootstrap service exits when the currently available queue is idle. Starting it again is safe;
all seeds, months, games, and probes are idempotent. Inspect it without mutating state with:

```sh
sudo -u bughouse-crawler /opt/bughouse/venv/bin/bughouse-explorer \
  crawl --crawler-db /opt/bughouse/data/crawler.db status
journalctl -u bughouse-crawler.service -f
systemctl list-timers bughouse-crawler-monthly.timer
```

Both services take the same `flock`, ensuring that only one crawler worker can run. The timer runs
at 03:00 UTC on day two and is persistent across downtime.

Back up `crawler.db` with SQLite's online `.backup` command, then copy the completed backup off-host.
Do not copy only the main file while it has an active WAL. The crawler database is irreplaceable;
the legacy opening index and future derived tree are rebuildable.

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

`data/games.db` is **not** in the repo. It belongs to the frozen explorer reference and is not
currently built by the crawler:

- **Upload an existing legacy copy:** checkpoint the WAL, then
  `rsync -a --partial --inplace data/games.db root@SERVER:/opt/bughouse/data/` and
  `chown bughouse:bughouse` it. Restart the service afterward.

The future crawler-to-index adapter will replace this manual legacy database handoff.

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
