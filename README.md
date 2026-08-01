# Bughouse Opening Explorer Data Platform

A durable SQLite crawler for building a centralized collection of Chess.com
Bughouse games.

This project is a modified continuation of the original
[Bughouse Opening Explorer by Oh-My-Lands](https://github.com/Oh-My-Lands/bughouse-opening-explorer).
The original project supplied the opening-index, replay, read-server, and
frontend foundation that remains in this repository for reference. The current
development focus is the crawler and raw-data platform needed to make an online
opening explorer sustainable.

The project is licensed under the
[GNU Affero General Public License v3](https://www.gnu.org/licenses/agpl-3.0.html).
See [LICENSE](LICENSE) and
[Original work and license](#original-work-and-license).

## Purpose

The original explorer required each operator to download individual players'
games into a local database. This version replaces that acquisition workflow
with a single, resumable crawl that can:

- begin from a controlled set of seed players;
- retain only Bughouse games from Chess.com's monthly public archives;
- discover additional players through board participants and sampled partner
  games;
- qualify players using timestamped post-game ratings;
- ingest every available archive month for eligible players;
- refresh active players with new games each month; and
- expose persisted progress without running a separate dashboard.

The result is an authoritative raw-game database that can later feed an online
opening tree and the
[`bughouse-chess`](https://github.com/Ellipsoul/bughouse-chess) viewer.

This phase does **not** provide a public game API or a deployed opening
explorer. The legacy indexer, read server, and frontend are intentionally frozen
until they are ported to consume the crawler database.

## How the crawl expands

```text
approved seeds
    -> recent archive qualification scans
    -> complete lifetime archives for eligible players
    -> deterministic callback probes for partner boards
    -> partner-board players and rating observations
    -> newly eligible players
    -> repeat until the reachable queue is exhausted
```

A player qualifies when a Bughouse board ending inside the run's
one-calendar-year window records a post-game rating of at least 2000. Seeds are
not exempt. A candidate can qualify on a later encounter, and a dormant player
can reactivate when new qualifying evidence appears.

Partner enrichment uses at most one deterministic probe per eligible player and
calendar year, restricted to boards inside the rolling eligibility window. An
initial full crawl therefore creates no more than two samples when the one-year
window crosses New Year. Samples are created only after the player's lifetime
archive is complete, and a partial current-year choice remains fixed as later
monthly games arrive.

The crawler follows the transitive eligible population reachable from the seeds.
Chess.com does not expose a global Bughouse feed, so it cannot guarantee
discovery of disconnected players.

## Quickstart

```bash
git clone https://github.com/Ellipsoul/bughouse-opening-explorer.git
cd bughouse-opening-explorer

python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

# Create or migrate data/crawler.db.
bughouse-explorer crawl migrate

# Load the bundled operator-approved seed manifest.
bughouse-explorer crawl seed

# Stop after 100 players have completed their lifetime crawls.
bughouse-explorer crawl bootstrap --max-players 100
```

The default `CHESSCOM_USER_AGENT` identifies this repository and includes the
operator contact address `aronteh.chess@gmail.com`. Forks and deployments with a
different operator should override it.

Monitor the crawler from another terminal:

```bash
bughouse-explorer crawl status --watch
bughouse-explorer crawl status --json
```

Active crawl commands also print one timestamped `START` and outcome line per
job, including the current player/month and fetched Bughouse counts. This output
remains visible when the command runs inside tmux or a systemd journal.
HTTP anomalies are logged separately: rate limits, server errors, network
timeouts, retry delays, recoveries, and successful responses slower than ten
seconds. Their aggregate counters are persisted in the run status.

Stop with Ctrl-C and continue safely:

```bash
bughouse-explorer crawl resume

# Preserve the original eligibility cutoff when continuing a particular run.
bughouse-explorer crawl resume RUN_ID

# After changing sampling policy, rebuild only unfinished probe work.
bughouse-explorer crawl rebuild-probes RUN_ID

# Reconcile historical terminal 404s and stranded completion work while stopped.
bughouse-explorer crawl reconcile RUN_ID
```

Refresh both the previous calendar month and the still-changing current month
for active eligible players:

```bash
bughouse-explorer crawl monthly

# Explicit replay for an operator-selected month.
bughouse-explorer crawl monthly --year 2026 --month 7
```

## Configuration

| Variable                   | Default               | Purpose                                       |
| -------------------------- | --------------------- | --------------------------------------------- |
| `BUGHOUSE_CRAWLER_DB`      | `data/crawler.db`     | Raw games, crawl state, and progress          |
| `CHESSCOM_USER_AGENT`      | Repository URL + operator email | Contact-bearing HTTP identity       |
| `CHESSCOM_MIN_INTERVAL_MS` | `100`                 | Minimum interval between Chess.com requests   |
| `BUGHOUSE_SAMPLER_VERSION` | `2`                   | Deterministic annual partner-sampling policy version |
| `BUGHOUSE_MAX_CONSECUTIVE_ERRORS` | `5`            | Stop after this many consecutive job errors          |

The crawler uses one synchronous worker and one HTTP request at a time. It sends
ETag and Last-Modified validators, honours Retry-After, backs off on transient
failures, and stores retries in the durable queue instead of losing work when
the process exits. Archive scheduling has a hard lower bound of January 2016,
when Bughouse became available on Chess.com.

Current-month archive responses are partial snapshots. Every bootstrap, resume,
and monthly refresh requeues that UTC month for active players; UUID upserts
append newly published games without duplicating boards already stored.

## SQLite data model

The crawler owns `data/crawler.db`, opened in WAL mode. Its numbered migrations
live under `bughouse_explorer/crawler/sql/`.

- `players` stores normalized identities, eligibility state, discovery
  provenance, and qualifying evidence.
- `games` stores canonical board UUIDs, numeric and partner references, moves,
  metadata, original JSON, and content hashes.
- `game_participants` stores board colors, players, results, ratings, and rating
  provenance.
- `player_months` is the monthly archive ledger with validators, counts,
  attempts, and errors.
- `player_archive_month_manifest` records the authoritative month set that must
  be successful or terminal unavailable before lifetime completion.
- `partner_year_samples` records the frozen, versioned annual callback choice
  for each eligible fully crawled player.
- `crawl_runs`, `crawl_jobs`, and `crawl_events` provide durable execution,
  leases, heartbeats, retries, and progress history.

Status includes explicit terminal-unavailable outcomes and a closure audit. A
drained queue is not reported complete while failed work or an eligible player
without a completed/terminal outcome remains.

Public monthly archives are authoritative. Callback-derived partner boards are
stored immediately and upgraded if the same board later appears in a public
archive. Callback failures do not roll back successful public-archive ingestion.

See the [documentation map](docs/README.md) for the current handoff, detailed
crawler policy, measured run analysis, and the full data/index/API roadmap.

## Repository layout

```text
bughouse_explorer/
  crawler/       active HTTP, policy, persistence, durable jobs, migrations, and CLI
  tcn.py         retained TCN decoder
  engine.py      retained single-board Bughouse replay engine
  indexer.py     frozen legacy position-graph reference
  db.py          frozen legacy index schema
  server.py      frozen read API and frontend server
frontend/        frozen original Vite/TypeScript explorer for later UI reference
deploy/          crawler and legacy-reference systemd examples
tests/           crawler, replay, TCN, and legacy-index regression coverage
```

The legacy reference commands remain available for an existing prebuilt
`data/games.db`:

```bash
bughouse-explorer index --db data/games.db
bughouse-explorer serve --db data/games.db
```

They do not currently read `data/crawler.db`.

## Tests

```bash
pytest
```

Live Chess.com requests are kept out of the ordinary test suite. Tests use
temporary SQLite databases and boundary fixtures so normal development does not
consume API capacity.

## Roadmap

1. Prove the crawler sustainable over the approved seed population and monthly
   refresh cycle.
2. Port the retained TCN replay/indexing logic to build an incremental opening
   tree from `data/crawler.db`.
3. Expose a versioned read API for positions, moves, games, usernames, and FEN
   lookup.
4. Implement the opening-explorer interface inside `bughouse-chess` rather than
   maintaining a second production frontend.

## Original work and license

This repository is based on
[Oh-My-Lands/bughouse-opening-explorer](https://github.com/Oh-My-Lands/bughouse-opening-explorer).
Its Git history is retained so the original authorship and subsequent
modifications remain traceable. The original replay engine, TCN decoder,
position index, read server, frontend, and associated tests remain valuable
reference implementations.

The project continues to be distributed under the **GNU Affero General Public
License, version 3 or later**. The full license text is in [LICENSE](LICENSE).
Modified versions must preserve the applicable notices and comply with the
AGPL's corresponding-source requirements, including when a modified version is
made available to users over a network.
