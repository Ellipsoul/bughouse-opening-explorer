# Bughouse Opening Explorer Data Platform

A durable SQLite crawler for building a centralized collection of Chess.com
Bughouse games.

This project is a modified continuation of the original
[Bughouse Opening Explorer by Oh-My-Lands](https://github.com/Oh-My-Lands/bughouse-opening-explorer).
The original project supplied the opening-index, replay, read-server, and
frontend foundation that remains in this repository for reference. The current
raw crawl, qualification-correctness, accepted recovery milestone, and full
local derived opening tree are complete. The immediate product focus is an
approval-gated hosted trial of that immutable packed artifact and a bandwidth-
conscious online explorer.

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
- ingest every available archive month when a player first qualifies;
- refresh every once-qualified player with new games each month, permanently;
  and
- expose persisted progress without running a separate dashboard.

The result is an authoritative raw-game database that will feed an online
opening tree and the
[`bughouse-chess`](https://github.com/Ellipsoul/bughouse-chess) viewer.

The public browser receives only bounded opening-neighborhood responses; it
never receives the raw database or packed artifact. A representative opening
service and one-board explorer are deployed, while the full artifact remains
local pending a separately approved preview trial.

## Platform direction

```text
validated restored crawler snapshot (lossless raw truth copy)
        ↓
versioned packed-position-graph-v1 artifact
        ↓
state-qualified read-only FastAPI service
        ↓
graph-aware bughouse-chess Next.js interface
```

The raw crawler database remains ordinary, lossless, queryable SQLite and is
never sent to a browser. The opening graph is a separately rebuildable,
read-optimized snapshot. Piece placement is canonical node identity; side to
move, castling, and en-passant remain state-qualified navigation context. The
API serves bounded, versioned node/state/edge responses, and the client loads
only the data required for the current navigation.

The transposition contract, edge cases, rehearsal measurements, and full-build
gate are recorded in
[`docs/OPENING_POSITION_GRAPH_REFACTOR_2026-09-01.md`](docs/OPENING_POSITION_GRAPH_REFACTOR_2026-09-01.md).

See [`docs/PLATFORM_ARCHITECTURE.md`](docs/PLATFORM_ARCHITECTURE.md) for the
layer contracts, publication lifecycle, bandwidth rules, and failure
isolation. See [`docs/BACKUP_RECOVERY.md`](docs/BACKUP_RECOVERY.md) for the
demonstrated backup and restore procedure that protects the raw source of truth.
The measured full build and current hosting recommendation are in
[`docs/FULL_OPENING_TREE_SCALE_UP_RESULT_2026-08-04.md`](docs/FULL_OPENING_TREE_SCALE_UP_RESULT_2026-08-04.md).

Player Insights follow a parallel snapshot-derived path: versioned analyzers
build an immutable, queryable SQLite artifact, deterministic browser-safe
projections are checked into `bughouse-chess`, and the public page imports them
at build time. The canonical extension and refresh contract is
[`docs/PLAYER_INSIGHTS_DEVELOPMENT_GUIDE.md`](docs/PLAYER_INSIGHTS_DEVELOPMENT_GUIDE.md);
the automated first-of-month procedure is
[`docs/MONTHLY_DATA_AND_PLAYER_INSIGHTS_RUNBOOK.md`](docs/MONTHLY_DATA_AND_PLAYER_INSIGHTS_RUNBOOK.md);
the reusable fresh-session blueprint is
[`docs/PLAYER_INSIGHTS_SESSION_PROMPT.md`](docs/PLAYER_INSIGHTS_SESSION_PROMPT.md).
The current shared artifact contains net material, Average King Height,
colour-aware Piece Drop Heat Maps, and bounded Material Game Highs. The newest
full extraction and static publication evidence are in
[`docs/PLAYER_MATERIAL_GAME_HIGHS_INSIGHTS_RESULT_2026-08-12.md`](docs/PLAYER_MATERIAL_GAME_HIGHS_INSIGHTS_RESULT_2026-08-12.md).

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
not exempt. Qualification permanently enrolls that player in game collection.
The eligible/dormant state continues to describe only whether qualifying
evidence is current; an enrolled player still receives monthly refreshes after
becoming dormant and can reactivate when new qualifying evidence appears.

Permanent tracking begins with the eligible cohort at the policy's introduction
on 1 August 2026. Players already dormant at that point are not retroactively
enrolled. A player who qualifies on or after that baseline remains enrolled if
they later become dormant.

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

## Monthly maintenance

Run the following command from the repository root on the first day of each
new month:

```bash
.venv/bin/bughouse-explorer crawl --crawler-db data/crawler.db monthly
```

For example, a run started on 1 September refreshes August, the newly completed
UTC month, and September, the still-changing current month. It does this for
every permanently tracked player whose archive is available. The command also
reconciles any interrupted lifetime work before processing the monthly queue.

New opponents found in those archives are evaluated from their timestamped
post-game ratings. If an observed player qualifies at 2000 or higher inside the
run's one-calendar-year window, the crawler permanently enrolls that player,
fetches their archive list, and queues every available Bughouse month back to
January 2016. Future monthly runs then keep that player updated even if they
later become dormant. The 1,153 players who were already dormant when permanent
tracking was introduced on 1 August 2026 remain outside this cohort.

The operation is idempotent: archive validators and UUID upserts make it safe to
repeat without duplicating games. Monitor it from another terminal with:

```bash
.venv/bin/bughouse-explorer crawl --crawler-db data/crawler.db status --watch
```

`Ctrl-C` records a graceful stop and leaves queued work durable. Use the run id
shown by `crawl status` to preserve the original evaluation cutoff when
continuing:

```bash
.venv/bin/bughouse-explorer crawl --crawler-db data/crawler.db resume RUN_ID
```

To deliberately replay a different historical month, supply it explicitly:

```bash
.venv/bin/bughouse-explorer crawl --crawler-db data/crawler.db monthly \
  --year 2026 --month 7
```

The production systemd timer in `deploy/bughouse-crawler-monthly.timer` runs the
same default command at 03:00 UTC on the first day of each month.

To continue from raw acquisition through a checked immutable snapshot, one
shared rebuild of every registered Player Insight, deterministic projection
validation, and optional local frontend replacement, follow the automated
[`monthly data and Player Insights runbook`](docs/MONTHLY_DATA_AND_PLAYER_INSIGHTS_RUNBOOK.md).

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

Current-month archive responses are partial snapshots. Bootstrap, resume, and
monthly runs requeue that UTC month for all permanently tracked players. UUID
upserts append newly published games without duplicating boards already stored.

## SQLite data model

The crawler owns `data/crawler.db`, opened in WAL mode. Its numbered migrations
live under `bughouse_explorer/crawler/sql/`.

- `players` stores normalized identities, current eligibility state, discovery
  and qualifying evidence, and the durable `tracking_started_at` enrollment
  marker.
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
drained queue is not reported complete while failed work or a permanently
tracked player without a completed/terminal outcome remains.

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
