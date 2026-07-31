# SQLite Bughouse crawler

The crawler builds a durable raw-data foundation before the opening tree or web UI is ported. It
uses a separate SQLite database from the legacy explorer because the two stores have different
lifecycle and schema requirements.

## Scope and data flow

```text
approved seeds
    -> public archive lists
    -> recent-month qualification scan
    -> complete lifetime archives for eligible players
    -> deterministic callback probes
    -> partner boards and four-player rating observations
    -> newly eligible players
```

Coverage is the transitive eligible population reachable from the seeds. Chess.com has no global
Bughouse feed, so disconnected populations cannot be discovered by this strategy.

Only Bughouse records are retained. Public monthly archives are authoritative. Callback boards are
stored immediately and upgraded if the same UUID later appears in a public archive. Original JSON,
content hashes, TCN, FEN, numeric ids, UUIDs, and partner references are kept for later indexing and
correction handling.

## Eligibility and discovery

A timestamped post-game rating qualifies when it is at least 1800 and the board ended on or after
the run's exact two-calendar-year cutoff. The boundary is inclusive. Seeds are candidates, not
exceptions: their recent archives are scanned newest-first, and lifetime work is queued only after
qualifying evidence appears.

Every public board records both players. A callback rating can qualify a player only when it came
from a timestamped `WhiteElo` or `BlackElo` PGN header; a callback profile rating is stored but does
not qualify. Candidates can qualify on any later encounter. Eligible players whose newest
qualifying evidence falls outside the window become dormant during the monthly run; stored history
is retained, and later qualifying evidence reactivates them.

## Partner sampling

Sampling is adaptive for each player-month:

- 1-4 Bughouse boards: probe all;
- 5-20: probe one board from each chronological half; and
- over 20: probe one board.

Within each stratum the winner has the lowest BLAKE2 hash of
`sampler-version | username | year | month | board-uuid`. Selection is deterministic across stops
and restarts, and the sampler version is stored in the job payload and month ledger. Probe jobs are
globally de-duplicated by board UUID.

The callback accepts numeric ids and UUIDs. Its partner reference is stored as text, fetched only
when not already known, and resolved to reciprocal board UUIDs when both boards are present. A 404
is retried daily three times after its initial attempt, then retained as a failed unresolved probe.
All other callback enrichment failures leave the public archive month committed.

## SQLite schema and transactions

Numbered migrations live in `bughouse_explorer/crawler/sql`. The database enables foreign keys,
WAL journaling, a busy timeout, and normal synchronous mode on every connection.

- `players`: normalized identity, display casing, candidate/eligible/dormant state, evidence, and
  crawl completion timestamps.
- `games`: canonical board UUID, numeric and partner ids, move/source metadata, original JSON, and
  content hash.
- `game_participants`: board color, normalized player, post-game Elo, result, and rating source.
- `player_months`: archive status, validators, counts, attempts, sampler version, and error.
- `crawl_runs`: configuration snapshot, heartbeat, counters, and terminal status.
- `crawl_jobs`: unique durable job, payload, availability, retry budget, and expiring lease.
- `crawl_events`: timestamped completion and error history used by status reporting.

HTTP calls occur outside SQLite transactions. A successful month commits its public boards,
participants, eligibility changes, newly discovered full-crawl/probe jobs, HTTP validators, and
month completion together. UUID and job-key uniqueness makes replay idempotent. `BEGIN IMMEDIATE`
serializes leasing, and an expired lease is automatically reclaimed after interruption.

## HTTP policy

There is one synchronous worker and one shared client, so exactly one request is in flight. The
client waits at least `CHESSCOM_MIN_INTERVAL_MS` (250 ms by default) plus small jitter between
completed requests. It sends conditional validators for repeat month requests, honours numeric
`Retry-After`, and retries network errors, 429s, and 5xx responses with exponential backoff capped
at 60 seconds. Exhausted immediate attempts defer the durable job instead of terminating the run.

Set `CHESSCOM_USER_AGENT` to a useful contact-bearing value before an unattended crawl, following
[Chess.com's serial-access guidance](https://www.chess.com/news/view/published-data-api).

## Commands and progress

```text
bughouse-explorer crawl migrate
bughouse-explorer crawl seed USERNAME...
bughouse-explorer crawl bootstrap [--max-jobs N]
bughouse-explorer crawl monthly [--year YYYY --month MM] [--max-jobs N]
bughouse-explorer crawl resume [RUN_ID] [--max-jobs N]
bughouse-explorer crawl status [--watch] [--json]
```

Status is read-only and reports candidate/eligible/dormant/fully-crawled players, queue states,
current job/player/month, boards and resolved partner links, request counters and rate, retries,
heartbeat, recent job throughput, remaining queue size, and the latest persisted error.

## Operations

The files under `deploy/` provide a manually started bootstrap service and a monthly systemd timer.
Keep `data/crawler.db`, its WAL/SHM sidecars, and credentials writable/readable only by the crawler
service account. SQLite is local-only by construction and must never be served directly to a
browser.

Use SQLite's online backup command while the crawler may be running:

```bash
sqlite3 /opt/bughouse/data/crawler.db \
  ".backup '/opt/bughouse/backups/crawler-$(date -u +%F).db'"
```

Copy the completed backup off-host nightly with the operator's backup system. Raw/crawl data is
irreplaceable; the future positions, moves, facts, and aggregates should remain rebuildable.

## Deferred phases

Phase 2 will port TCN replay and indexing to consume `games` and build an incremental online
opening tree plus a versioned read API. Phase 3 will implement the interface inside the existing
`bughouse-chess` Next.js application, reusing its replay models and components. PostgreSQL can be
reconsidered only if measured SQLite concurrency or database-size limits justify that operational
cost; no such dependency is required for the crawler phase.
