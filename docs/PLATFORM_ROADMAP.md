# Crawler-to-online-platform roadmap

This document preserves the research and implementation plan beyond the
completed seed-reachable crawl. It is intentionally evidence-led: benchmark
cloned data before changing the irreplaceable raw store or choosing hosting
architecture. Final closure and data-quality measurements are recorded in
[`CRAWL_RUN_FULL_ANALYSIS.md`](CRAWL_RUN_FULL_ANALYSIS.md).

## Completed closure milestone

The crawler milestone was not merely “the process exited.” It required a
verified transitive closure run in which:

- every seed-reachable player with a qualifying observation has a completed
  lifetime crawl, where an explicitly recorded terminal-unavailable public
  month counts as processed;
- no queued, leased, or deferred archive/discovery work remains;
- failed jobs have been reconciled rather than ignored, including durable notes
  for terminal-unavailable public-month 404s;
- the current partial month is understood to remain mutable and scheduled for
  later maintenance;
- sampler-v2 annual probes have reached completion or a recorded unresolved
  terminal state;
- a consistent database backup passes integrity checks and exists off-host;
- final population, request, failure, throughput, and storage measurements are
  written down.

Run `8210df08-c748-4de7-9eea-ccc8740caa8a` satisfied those conditions on
1 August 2026: 1,014 lifetime crawls completed, one eligible archive was
explicitly terminal unavailable, all 52,890 jobs reached terminal completion,
and the final 8,195,984-board database passed integrity and structural audits.
This is closure of the population reachable from the seed set, not proof that
every Chess.com Bughouse player globally was found.

The next major product outcome is now a verified derived opening-index slice:
an adapter from crawler records, explicit quality/provenance policy, measured
index size and build speed on a clone, and representative read latency. The raw
database must remain lossless and independently recoverable.

## Workstream A — uncapped closure crawl (complete)

### Completion record

The 100-player and 250-player checkpoints, sampler-v2 retrofit, completion
safety migration, reconciliation, checked pre-launch backup, uncapped tmux run,
and final data audit are complete. The exact final measurements and anomaly
register are in `CRAWL_RUN_FULL_ANALYSIS.md`.

The historical uncapped continuation command was:

```bash
.venv/bin/bughouse-explorer crawl resume \
  8210df08-c748-4de7-9eea-ccc8740caa8a
```

It intentionally omitted `--max-players`. The run is now complete; do not
resume it for ordinary freshness maintenance. Use a new monthly run with a new
evaluation timestamp.

### Safe future maintenance operation

Pausing a future monthly or bootstrap run is safe. Send `Ctrl-C`, confirm the
run status became `stopped`, and later resume the same run id. An in-flight
request may leave a leased job; lease expiry recovers it idempotently. Avoid
force-killing SQLite during a commit when a graceful interrupt is available.

For a several-day run, tmux is adequate but systemd is safer: it gives restart
policy, a persistent journal, resource limits, and explicit service ownership.
Regardless of launcher, do not run two crawler workers against the same queue;
the policy is intentionally serial and the API pacing assumption depends on it.

### Historical checkpoints and convergence

The completed uncapped run used snapshots every 25 or 50 newly completed
players. Preserve the same measurements for any future population rebuild:

- eligible, dormant, and fully crawled players;
- archive-list/month/probe jobs by state and mode;
- new full archive jobs created since the last checkpoint;
- public and callback requests plus retry classes;
- unique boards and participant rows;
- database bytes and `dbstat` bytes by table/index;
- failed and deferred jobs with exact payload/error;
- wall time and completed jobs/hour.

The key convergence metric is:

```text
new full-history archive jobs / newly completed full crawls
```

It must remain below one and trend toward zero before final population and time
estimates become stable. Queue length alone is misleading because archive-list
jobs lazily create month jobs.

### Failure modes worth unattended monitoring

- disk exhaustion as raw games and indexes grow;
- SQLite corruption or host failure without an off-host backup;
- new failed jobs or terminal outcomes increasing unexpectedly;
- repeated 429/5xx/network failures creating deferred debt;
- callback schema changes or prolonged 404s;
- tmux/session or laptop shutdown stopping the worker;
- a stale run heartbeat with no active process;
- a process running older loaded code after the working tree changes;
- an unexpectedly rising closure ratio that makes time and disk forecasts
  invalid.

The current retry strategy handles ordinary transient HTTP failures; a
configurable consecutive-error circuit breaker stops sustained failure bursts.
The systemd example restarts crashes, uses `flock`, and can resume a fixed run
through `BUGHOUSE_RUN_ID`. Disk and off-host backup monitoring remain external.

## Workstream B — lossless raw database reduction

### Measured baseline

At approximately `2026-08-01 09:30 UTC`:

- `data/crawler.db`: 11,929,755,648 bytes (about 11.1 GiB);
- 6,460,556 canonical boards;
- `games` B-tree: about 8.315 GiB;
- raw JSON logical bytes: about 4.92 GiB;
- TCN logical bytes: about 0.49 GiB;
- `game_participants` table: about 0.896 GiB;
- participant primary-key autoindex: about 0.701 GiB;
- player/game participant lookup index: about 0.660 GiB;
- no freelist pages at the measurement point.

A deterministic 10,000-row sample compressed each raw JSON payload separately
with zlib level 6 from 7.80 MiB to 4.77 MiB, a ratio of 0.611. Median payload
size fell from 823 to 512 bytes. Extrapolated only as a first estimate, this
could save roughly 1.9 GiB of the current raw JSON while preserving it exactly.
Benchmark zstd as well; do not standardize on zlib from this one sample.

### Ranked experiments

1. **Compress archival JSON per row.** Store the exact response object as a
   zstd or zlib BLOB with an explicit codec/version. Normal crawl/query paths do
   not need to decode it; audit and correction tools can. Compare compression
   ratio, ingestion CPU, random-row decode latency, migration time, and backup
   behavior.
2. **Use an internal integer game key.** Retain board UUID as a unique external
   identifier, but reference an `INTEGER PRIMARY KEY` from participant and
   derived tables. Repeating a compact integer instead of a 36-byte UUID across
   roughly 12.9 million rows and multiple indexes should materially reduce
   table/index size. This is lossless but requires a carefully rehearsed schema
   migration.
3. **Store hashes in binary.** The SHA-256 content hash is currently a 64-byte
   hexadecimal string; a 32-byte BLOB preserves the same digest. UUIDs could
   also be stored as 16-byte binary values while formatting text at boundaries,
   though migration and debugging complexity must be weighed against savings.
4. **Separate hot normalized data from cold archival payloads.** A dedicated
   compressed archive table or sidecar database can keep serving/index scans
   narrow while preserving exact source JSON. Back up both atomically or with a
   shared snapshot protocol.
5. **Remove reconstructible hot columns only when the compressed original is
   retained and verified.** URLs may often be reconstructible from numeric ids,
   and much normalized metadata is duplicated in raw JSON. Any removal must be
   proven lossless across public and callback payload variants.
6. **Benchmark page and index design.** Page size, covering indexes, `WITHOUT
   ROWID`, and index column order may help, but current `dbstat` shows that raw
   payload and repeated UUIDs are much larger targets than crawl-control tables.

### Safe evaluation protocol

Never prototype compression by mutating the only live database.

1. Stop or use SQLite's online backup to create a consistent clone.
2. Run `PRAGMA quick_check` before the experiment.
3. Apply one candidate change at a time.
4. Verify row counts, UUID sets, content hashes, participant mappings, source
   payload round-trips, and representative TCN replay.
5. Record database and individual B-tree bytes with `dbstat` after `VACUUM`.
6. Benchmark ingestion and representative reads.
7. Keep the original clone until restoration has been demonstrated.

Compression of the raw database and compression of HTTP responses are separate
concerns. Chess.com transport encoding does not reduce stored SQLite pages.

## Workstream C — derived opening tree

### What the retained reference implementation does

The frozen indexer replays each board's TCN from the normal starting position,
up to a configurable ply depth. It builds:

- `positions`: unique position identity as four-field FEN plus an indexed
  64-bit BLAKE2 hash, with full FEN verification on lookup;
- `moves`: unique `(parent_position, move)` edges with SAN, squares, drop piece,
  and child position;
- `game_facts`: one `(position, move, game)` fact carrying outcome and rating
  sum for aggregation/filtering;
- `games_meta`: player, rating, outcome, URL, time-control, and date facts;
- `move_agg`: precomputed default-threshold counts and results per move.

The indexer already supports incremental UUID anti-join, buffered writes, WAL
checkpointing, and a disk-backed `VACUUM`. It intentionally counts a game once
per distinct `(position, move)` even if repetition revisits that transition.

The current comments describe a prior database with roughly 47 million
`game_facts` and expensive root queries around 1.3 million facts. Those figures
are reference evidence, not forecasts for the much larger crawler corpus.

### Required port and measurements

1. Add an adapter from crawler `games` and `game_participants` to the indexer's
   expected board/player/result shape. Index public authoritative boards; define
   whether callback-only boards are excluded until upgraded.
2. Preserve board UUID, content hash, and an index version so changed source
   payloads can invalidate and rebuild a game's facts safely.
3. Build a representative subset first. Measure games/second, positions,
   edges, facts per game, peak RAM, WAL growth, final bytes by B-tree, and query
   latency by depth.
4. Decide maximum indexed ply from product value and measured explosion. The
   explorer does not necessarily need full games to answer opening questions.
5. Keep raw/crawl tables irreplaceable and derived tables rebuildable. A
   separate read-optimized SQLite database or immutable snapshot is likely
   cleaner than serving the actively written crawler database.
6. Measure incremental updates and correction handling before designing the
   monthly production build.

The dominant size risk is `game_facts`: it grows approximately with indexed
plies per unique game. Position and move de-duplication does not similarly
de-duplicate per-game facts because filters and example-game lookup need game
membership.

## Workstream D — read API, latency, and bandwidth

### Existing server behavior

The frozen FastAPI server exposes:

- `/api/meta` for root id and indexed depth;
- `/api/usernames` for autocomplete counts;
- `/api/moves` for continuations and win/draw/loss counts;
- `/api/games` for representative high-rated games through a position;
- `/api/position` for FEN-to-position lookup.

The default unfiltered move query is already a keyed lookup against
`move_agg`. Arbitrary rating filters aggregate matching `game_facts` live.
Username filters instead drive from indexed `games_meta` usernames into
`idx_facts_game`, avoiding a scan of every game at a busy position. The server
uses per-process LRU caches of 4,096 move and game query variants. Multiple
Uvicorn workers provide separate SQLite connections and separate caches.

The frozen browser fetches small JSON, never the database. On navigation it
currently waits for `/api/moves`, renders the board/continuations, then awaits
`/api/games`. It does not prefetch child branches, and rapid navigation has no
request cancellation or stale-render guard.

### Scaling strategy to test

1. **Keep navigation keyed by compact position ids.** Return child ids and FENs
   with move rows as the reference API does.
2. **Materialize the overwhelmingly common paths.** Preserve `move_agg` for the
   default view. Consider a small number of product-defined rating buckets if
   arbitrary rating thresholds make live aggregation too costly; measure before
   multiplying aggregates.
3. **Fetch panels concurrently.** Moves and representative games can start
   together, while moves retain render priority.
4. **Prefetch narrowly.** After rendering a position, prefetch continuations for
   only the top `K` likely child moves, initially `K=2` or `3` and depth one.
   Cache by `(dataset_version, position_id, rating/filter tuple)`. Do not
   recursively prefetch the tree: branching causes exponential request and
   bandwidth growth.
5. **Use cancellation and stale-response protection.** An `AbortController` or
   navigation generation id should prevent a slow prior position from
   overwriting a later one.
6. **Consider a bounded branch endpoint.** One API call could return the current
   position plus top-child summaries, but it must enforce maximum nodes, depth,
   and encoded bytes. Compare it with ordinary HTTP/2 parallel keyed requests.
7. **Exploit immutable dataset versions.** Serve a read-only snapshot with a
   version id and strong ETags. CDN/browser caching can then retain popular
   position responses safely until a new index snapshot is published.
8. **Keep username autocomplete separate and lazy.** The reference frontend
   already loads it after first paint. At hundreds of thousands of candidates,
   the production API should expose only indexed/eligible explorer users or a
   server-side prefix search rather than download every identity.
9. **Cap response payloads.** Move rows are naturally small; example games need
   a strict limit. Track compressed response bytes and cache hit rate alongside
   latency.
10. **Do not expose SQLite or crawl controls to browsers.** The public service
    is a versioned read API over a read-only derived database. Crawl mutation
    remains operator-only.

### Benchmark matrix

Measure cold and warm latency for:

- root and first five plies, which carry the most facts;
- a deep sparse position;
- default aggregate, rating-filtered, one-player, and exact-pair queries;
- FEN lookup;
- username prefix search;
- one-position versus bounded-branch responses;
- one, several, and many concurrent readers.

Record P50/P95/P99 server latency, rows scanned, database CPU, cache hit rate,
response bytes before/after HTTP compression, and client navigation time. Set
service-level targets only after the representative derived index exists.

SQLite may be entirely adequate for a single read host using immutable
snapshots, indexes, WAL/read-only connections, multiple API workers, and an
HTTP cache. Reconsider PostgreSQL or a distributed store only if measurements
show a concurrency, update, or operational limit that those techniques cannot
meet.

## Workstream E — publication and `bughouse-chess`

Publish derived index versions atomically: build and validate a new snapshot,
then switch the API to it and invalidate/version caches. Never expose a
partially rebuilt opening tree.

The final interface belongs in the existing `bughouse-chess` Next.js
application. Adapt the future API to its `ChessGame`, `MatchGame`, numeric game
id, UUID partner id, and player models. Reuse its board and replay components
where appropriate. The frozen Vite frontend is a behavior/reference source,
not the intended second production application.

Preserve the AGPL attribution and corresponding-source obligations when the
modified explorer is made available over a network. Keep the README's link to
the original Oh-My-Lands work and retain Git history.
