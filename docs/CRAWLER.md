# SQLite Bughouse crawler

The crawler builds a durable raw-data foundation before the opening tree or web
UI is ported. It uses a separate SQLite database from the legacy explorer
because the two stores have different lifecycle and schema requirements.

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

Coverage is the transitive eligible population reachable from the seeds.
Chess.com has no global Bughouse feed, so disconnected populations cannot be
discovered by this strategy.

Only Bughouse records are retained. Public monthly archives are authoritative.
Callback boards are stored immediately and upgraded if the same UUID later
appears in a public archive. Original JSON, content hashes, TCN, FEN, numeric
ids, UUIDs, and partner references are kept for later indexing and correction
handling.

## Eligibility and discovery

A timestamped post-game rating qualifies when it is at least 2000 and the board
ended inside the run's fixed one-calendar-year evaluation window:

```text
eligibility_cutoff(run_started_at) <= end_time <= run_started_at
```

Both boundaries are inclusive. Seeds are candidates, not exceptions: their
recent archives are scanned newest-first, and lifetime work is queued only
after qualifying evidence appears.

Every public board records both players. A callback rating can qualify a player
only when it came from a timestamped `WhiteElo` or `BlackElo` PGN header; a
callback profile rating is stored but does not qualify. Candidates can qualify
on any later encounter. Once a candidate qualifies, `tracking_started_at`
permanently enrolls that player in lifetime and monthly game collection.
Eligible players whose newest qualifying evidence falls outside the window
become dormant during the monthly run, but dormancy is only a current-rating
classification. For permanently enrolled players, stored history and pending
work are retained, monthly refreshes continue, and later qualifying evidence
reactivates them.

Public payloads are authoritative corrections as well as new observations. If
a public upsert replaces a participant identity or rating used by a player's
active qualifying pointer, the crawler recomputes that player's evidence from
their remaining authoritative `public` and `callback_pgn` observations inside
the same fixed window. This prevents a denormalized pointer from outliving its
participant row. Ordinary aging into dormancy does not end permanent tracking;
enrollment is removed only when the original qualification is demonstrably
invalid, not merely old.

The permanent cohort was initialized from players currently eligible when the
policy was introduced on 1 August 2026. The 1,153 players already dormant at
that point were deliberately excluded rather than retroactively assigned
lifetime work. New qualifications after that baseline permanently enroll the
player, even if their state later becomes dormant. The qualification audit
subsequently removed two invalid initial enrollments, leaving 1,013 tracked
players before the first routine monthly run.

## Partner sampling

Sampler version 2 creates at most one callback sample per eligible player and
calendar year, and considers only public boards on or after the run's rolling
eligibility cutoff. A one-year window normally intersects at most two calendar
years, so old lifetime history creates no stale callback debt. Samples are
created only after a player's full archive is complete.

The winner has the lowest BLAKE2 hash of
`sampler-version | username | year | board-uuid`. Selection is deterministic
across stops and restarts. The chosen board is persisted in
`partner_year_samples`; a current partial-year choice is frozen so later month
refreshes cannot enqueue a second probe for that player-year. Probe jobs remain
globally de-duplicated by board UUID, including when both board players select
the same game.

`crawl rebuild-probes RUN_ID` retrofits an existing stopped run. It preserves
completed probes and their callback data, removes every unfinished legacy probe,
and reconstructs the exact version-2 queue from authoritative public games
using the original run's eligibility cutoff. The operation refuses to proceed
while a partner probe is leased and is idempotent for the same database state.

The callback accepts numeric ids and UUIDs. Its partner reference is stored as
text, fetched only when not already known, and resolved to reciprocal board
UUIDs when both boards are present. A 404 is retried daily three times after its
initial attempt, then retained as a terminal unresolved outcome with its error,
attempts, and timestamp. All other callback enrichment failures leave the
public archive month committed.

## SQLite schema and transactions

Numbered migrations live in `bughouse_explorer/crawler/sql`. The database
enables foreign keys, WAL journaling, a busy timeout, and normal synchronous
mode on every connection.

- `players`: normalized identity, display casing, candidate/eligible/dormant
  state, evidence, permanent-tracking enrollment, and crawl completion
  timestamps.
- `games`: canonical board UUID, numeric and partner ids, move/source metadata,
  original JSON, and content hash.
- `game_participants`: board color, normalized player, post-game Elo, result,
  and rating source.
- `player_months`: archive status, validators, counts, attempts, sampler
  version, error, and terminal-unavailable audit fields.
- `player_archive_month_manifest`: the exact month set returned by the latest
  successful full archive-list request. Mutable maintenance months outside this
  manifest do not block lifetime completion.
- `partner_year_samples`: versioned, frozen player-year selections and the
  eligibility cutoff used to make them.
- `crawl_runs`: configuration snapshot, heartbeat, counters, and terminal
  status.
- `crawl_jobs`: unique durable job, payload, availability, retry budget, and
  expiring lease.
- `crawl_events`: timestamped completion and error history used by status
  reporting.

HTTP calls occur outside SQLite transactions. A successful month commits its
public boards, participants, eligibility changes, newly discovered full-crawl
jobs, HTTP validators, and month completion together. Annual probe scheduling
runs after full-crawl completion and is independently idempotent. UUID and
job-key uniqueness makes replay safe. `BEGIN IMMEDIATE` serializes leasing, and
an expired lease is automatically reclaimed after interruption.

## HTTP policy

There is one synchronous worker and one shared client, so exactly one request is
in flight. The client waits at least `CHESSCOM_MIN_INTERVAL_MS` (100 ms by
default) plus small jitter between completed requests. It sends conditional
validators for repeat month requests, honours numeric `Retry-After`, and retries
network errors, 429s, and 5xx responses with exponential backoff capped at 60
seconds. Each retry records its response status or exception type, elapsed time,
attempt, selected delay, and `Retry-After`; a later success records recovery.
Successful responses slower than ten seconds are also recorded. Exhausted
immediate attempts defer the durable job instead of terminating the run.

Public archive-month 404s are terminal unavailable outcomes. The player,
year/month, original HTTP error, and timestamp remain in `player_months`; the
month is not retried automatically and counts as processed for a full-archive
manifest. A full archive-list 404 is recorded separately on the player and does
not falsely set `full_crawl_completed_at`. Monthly refreshes exclude players
whose whole archive is terminal unavailable.

Transient HTTP exhaustion and other job errors contribute to a consecutive
error streak. Five consecutive errors stop the worker by default before a
sustained API or schema problem can damage a large queue. Override the positive
threshold with `BUGHOUSE_MAX_CONSECUTIVE_ERRORS`.

The default `CHESSCOM_USER_AGENT` includes this repository and the operator's
contact email. Override it when the operator changes, following
[Chess.com's serial-access guidance](https://www.chess.com/news/view/published-data-api).

## Commands and progress

```text
bughouse-explorer crawl migrate
bughouse-explorer crawl seed USERNAME...
bughouse-explorer crawl rebuild-probes [RUN_ID] [--sampler-version N]
bughouse-explorer crawl reconcile [RUN_ID]
bughouse-explorer crawl bootstrap [--max-jobs N] [--max-players N]
bughouse-explorer crawl monthly [--year YYYY --month MM] [--max-jobs N]
bughouse-explorer crawl resume [RUN_ID] [--max-jobs N] [--max-players N]
bughouse-explorer crawl status [--watch] [--json]
```

`--max-players N` stops when the database contains `N` players with completed
lifetime crawls; queued work remains durable for a later resume. Current-month
archives are mutable snapshots, so bootstrap and resume requeue the current UTC
month for permanently tracked players. The monthly command queues both the
selected/previous month and the current partial month for that same cohort,
including dormant players. Game UUID upserts make repeated snapshots
append-only and idempotent.

`crawl reconcile` is idempotent and also runs automatically at the start of a
monthly run. It converts legacy public 404 failures into terminal audit records
and queues a fresh full archive list for any permanently tracked player with
neither a completed lifetime crawl nor a durable completion path. It also
queues an archive-list-only provenance backfill for old completions that lack
`full_archive_list_fetched_at`. A successful list response records the exact
manifest, preserves already complete or terminal months, and queues only months
that are actually missing. It therefore does not normally re-download the
legacy players' complete histories.

January 2016 is the hard lower archive boundary because Chess.com did not offer
Bughouse earlier. Archive-list scheduling and explicit monthly refreshes both
enforce it. On startup, unfinished pre-2016 work left by an older crawler build
is discarded while already completed audit records are retained.

Status is read-only and reports candidate/eligible/dormant/fully-crawled
players, queue states, current job/player/month, boards and resolved partner
links, request counters and rate, retries, heartbeat, recent job throughput,
remaining queue size, and the latest persisted error.
It also reports terminal outcomes and a closure audit. A run is labelled
`complete` only when no queued, leased, deferred, or failed jobs remain and
every permanently tracked player is either fully crawled or has an explicit
terminal archive outcome.

Bootstrap, monthly, and resume commands stream timestamped job progress to the
terminal. Each job produces a `START` line followed by `DONE`, `DEFERRED`,
`TERMINAL`, or `FAILED`, with player/month context and ingestion counts. The
same output is captured by tmux and the systemd journal. HTTP anomaly counters
for retries, 429s, recoveries, timeouts, network errors, 5xx responses, slow
responses, and exhausted retry budgets remain available in run status JSON.

`Ctrl-C` records an interrupted stop. `SIGTERM` records a clean terminated stop,
so a service manager can distinguish an operator pause from a crash. An
explicit `resume RUN_ID` uses the original run timestamp consistently for both
qualification and dormancy evaluation.

## Operations

The files under `deploy/` provide a manually started bootstrap service and a
monthly systemd timer intended for the first of each month. Keep
`data/crawler.db`, its WAL/SHM sidecars, and
credentials writable/readable only by the crawler service account. SQLite is
local-only by construction and must never be served directly to a browser.

Use SQLite's online backup command while the crawler may be running:

```bash
sqlite3 /opt/bughouse/data/crawler.db \
  ".backup '/opt/bughouse/backups/crawler-$(date -u +%F).db'"
```

Copy the completed backup off-host nightly with the operator's backup system.
Raw/crawl data is irreplaceable; the future positions, moves, facts, and
aggregates should remain rebuildable.

Follow [`BACKUP_RECOVERY.md`](BACKUP_RECOVERY.md) for the complete recovery
contract, including source/restore capacity checks, compressed-artifact
checksums, independent SQLite validation, and an off-host restore drill.
Whole-file Zstandard is a cold backup transport only; it does not change the
live raw database or its query/parser contract.

## Deferred phases

Phase 2 will port TCN replay and indexing to consume `games` and build an
incremental online opening tree plus a versioned read API. Phase 3 will
implement the interface inside the existing `bughouse-chess` Next.js
application, reusing its replay models and components. PostgreSQL can be
reconsidered only if measured SQLite concurrency or database-size limits justify
that operational cost; no such dependency is required for the crawler phase.
The layer boundaries, publication lifecycle, API shape, and client-bandwidth
rules are defined in
[`PLATFORM_ARCHITECTURE.md`](PLATFORM_ARCHITECTURE.md).
