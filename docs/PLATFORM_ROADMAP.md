# Crawler-to-online-platform roadmap

This document preserves the research and implementation plan beyond the
completed seed-reachable crawl. It is intentionally evidence-led: benchmark
cloned data before changing the irreplaceable raw store or choosing hosting
architecture. Final closure and data-quality measurements are recorded in
[`CRAWL_RUN_FULL_ANALYSIS.md`](CRAWL_RUN_FULL_ANALYSIS.md).

The post-reconciliation backup and designated-directory read-back restore are
complete under the accepted accidental-deletion threat model. The immediate
product outcome is now the derived opening explorer, not live raw-database
compression. The durable layer boundaries and client-bandwidth design are defined in
[`PLATFORM_ARCHITECTURE.md`](PLATFORM_ARCHITECTURE.md).

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
- a consistent database backup passes integrity checks and a restore from the
  user-designated backup directory repeats the full validation suite;
- final population, request, failure, throughput, and storage measurements are
  written down.

Run `8210df08-c748-4de7-9eea-ccc8740caa8a` satisfied those conditions on
1 August 2026: 1,014 lifetime crawls completed, one eligible archive was
explicitly terminal unavailable, all 52,890 jobs reached terminal completion,
and the final 8,195,984-board database passed integrity and structural audits.
This is closure of the population reachable from the seed set, not proof that
every Chess.com Bughouse player globally was found.

The crawl/data and accepted recovery milestones are complete. The fresh backup
postdates the 86-row qualification reconciliation, and a read-back restoration
from the designated backup directory has been demonstrated. Host and volume
failure are explicitly outside the current threat model.

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

## Workstream B — lossless raw database reduction (deferred)

This remains useful research, but it is not the next objective and is not a
prerequisite for the opening explorer. `crawler.db` remains ordinary,
losslessly queryable SQLite. Any future live-storage change must preserve raw
payload round trips, parser behavior, normalized queries, and audit tooling on
a disposable clone before migration is considered.

### Measured baseline

After qualification reconciliation on 2 August 2026:

- `data/crawler.db`: 15,146,962,944 bytes (about 14.1 GiB);
- 8,195,984 canonical boards;
- `games` B-tree: 11,323,654,144 bytes (74.76% of the database);
- raw JSON logical bytes: 6,690,774,907;
- TCN logical bytes: 650,941,464;
- `game_participants` table: 1,224,667,136 bytes;
- participant primary-key autoindex: 955,781,120 bytes;
- player/game participant lookup index: 904,167,424 bytes;
- repeated textual game UUIDs occupy at least 885,166,272 logical bytes across
  `games` and `game_participants`, before index overhead;
- hexadecimal content hashes occupy 524,542,976 logical bytes; and
- no freelist pages were present at the measurement point.

The existing whole-database Zstandard snapshot is 3,160,490,471 bytes, about
79% smaller than the live SQLite file, but it is a cold recovery artifact that
must be decompressed before querying and predates the latest reconciliation.

A deterministic 10,000-row sample compressed each raw JSON payload separately
with zlib level 6 from 7.80 MiB to 4.77 MiB, a ratio of 0.611. Median payload
size fell from 823 to 512 bytes. Extrapolated only as a first estimate, this
could save roughly 2.4 GiB of the current raw JSON while preserving it exactly.
Benchmark zstd as well; do not standardize on zlib from this one sample.
This sample is directional evidence only and does not authorize a live schema
or payload-encoding change.

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

This is the next product workstream. Follow
`PLATFORM_ARCHITECTURE.md` so the raw store, derived snapshot, public API, and
client remain independently recoverable and testable.

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

### Required architecture and measurements

1. Use exact decoded move prefixes as trie-node identity. Transpositions remain
   separate. Pocket differences do not split a shared prefix; drops remain
   navigable edges and board placement is replayed for display.
2. Add a format-neutral adapter from crawler `games` and `game_participants` to
   the accepted board/player/result shape. Define whether callback-only boards
   are excluded until upgraded.
3. Preserve board UUID, content hash, and an index version so changed source
   payloads can invalidate and rebuild derived membership safely.
4. Measure prefix shape first: unique depth, nodes and branches by ply,
   identical complete lines, games ending at internal nodes, and compression
   from singleton termination and one-child runs.
5. Compare a compact relational baseline with a prefix-interval packed trie.
   Sorting games by move sequence makes every prefix a contiguous game-ordinal
   range; benchmark per-player White/Black sorted postings and compressed
   bitmaps for filtered rank/intersection queries.
6. Build representative subsets with identical input and query fixtures.
   Measure games/second, nodes, edges, membership, peak RAM, temporary/write-
   amplification/final bytes, and cold/warm filtered and unfiltered latency.
7. Keep raw/crawl tables irreplaceable and derived artifacts rebuildable. Serve
   an immutable version, never the actively written crawler database.
8. Measure correction handling, deterministic rebuild, atomic publication, and
   rollback before designing the monthly production build.

The representative comparison is complete. The selected format is the packed
prefix-interval trie with sorted White/Black ordinal postings; compact SQLite is
retained as the oracle and operational baseline, and dense compressed bitmaps
were rejected. The revised production policy excludes non-checkmate games of
six plies or fewer while retaining 431 short checkmates. It yields 6,516,478
games, 11,625,223 nodes, and 96,570,295 relational memberships, with projections
of about 3.23 GiB packed and 5.38 GiB SQLite. See
`OPENING_TREE_ARCHITECTURE_PROTOTYPE_2026-08-03.md` for the evidence.

The remaining Workstream C gate is implementation, not representation choice:
add the revised policy to the adapter, replace the object-retaining prototype
with a streaming/external-sort writer, compact the metadata component, and
repeat representative capacity/publication benchmarks before any full build.

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

The next experiment keeps the browser/database boundary but changes both sides
behind it. A localhost read service memory-maps the selected packed artifact,
and a local-only `bughouse-chess` route queries that service. The browser must
not load the complete artifact into JavaScript memory. Once measured locally,
the same query boundary can move to a hosted read service without rewriting the
client navigation state.

### Scaling strategy to test

1. **Keep navigation keyed by compact trie-node ids.** Return child ids and
   enough move/path data to replay the displayed board. FEN is a projection,
   not node identity.
2. **Use packed interval support and result postings for common paths.** Avoid
   reconstructing default branch counts from game metadata. Consider a small
   number of product-defined rating buckets only if arbitrary rating thresholds
   prove too costly; measure before multiplying aggregates.
3. **Fetch panels concurrently.** Moves and representative games can start
   together, while moves retain render priority.
4. **Prefetch a budgeted neighborhood.** Always return the current node and
   every immediate child, then expand a high-support descendant's complete
   immediate move list as one atomic group toward a target depth (initially
   five) only while hard node and encoded-byte budgets permit.
   Depth alone is unsafe: the revised trie contains about 97,057 nodes from the
   root through ply five. Return flat node/edge records plus explicit frontier
   ids rather than an unbounded recursive tree.
5. **Use cancellation and stale-response protection.** An `AbortController` or
   navigation generation id should prevent a slow prior node from
   overwriting a later one.
6. **Cache and refill by frontier.** Merge immutable structural records by
   `(dataset_version, node_id)` and cache filtered overlays by normalized filter
   tuple. Pin the visited path and its cached immediate move lists so backward
   moves are complete and local. Refill when the selected child is absent or
   idle prefetch approaches a frontier; deduplicate overlapping requests and
   record unused evicted prefetch.
7. **Exploit immutable dataset versions.** Serve a read-only snapshot with a
   version id and strong ETags. CDN/browser caching can then retain popular
   node responses safely until a new index snapshot is published.
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

The leading neighborhood endpoint is an experimental contract. Start with
conservative candidate limits such as target depth five, 2,000 default nodes,
a 4,000-node hard cap, 256 KiB default encoded bytes, and a 512 KiB hard cap.
Measure and revise them rather than treating them as production guarantees.

### Benchmark matrix

Measure cold and warm latency for:

- root and first five plies, which carry the most facts;
- a deep sparse position;
- default aggregate, rating-filtered, one-player, and exact-pair queries;
- FEN lookup;
- username prefix search;
- one-position versus bounded-branch responses;
- one-request-per-move, fixed-depth one/three/five, and adaptive budgeted
  neighborhood responses;
- popular forward navigation, branch-and-backtrack, cache-warm reverse
  navigation, deep links, and filter changes;
- one, several, and many concurrent readers.

Record P50/P95/P99 server latency, rows scanned, database CPU, cache hit rate,
response bytes before/after HTTP compression, requests per move, blocked clicks,
unused prefetched nodes, and client navigation/render time. The local prototype
should report cached versus network-backed interactions separately. Set final
service-level targets only after the representative packed service exists.

The packed artifact is selected for the first read-service experiment; SQLite
remains its correctness and operational fallback. Reconsider PostgreSQL or a
distributed store only if measured hosted concurrency or publication behavior
exposes a requirement that an immutable packed reader plus HTTP cache cannot
meet.

## Workstream E — publication and `bughouse-chess`

Publish derived index versions atomically: build and validate a new snapshot,
then switch the API to it and invalidate/version caches. Never expose a
partially rebuilt opening tree.

The API must return bounded neighborhood data rather than a database or full
tree. Prototype this first against a local memory-mapped artifact. Measure
response bytes, cancellation, frontier refill, request deduplication, cached
backtracking, and unused prefetch as part of the product slice; do not treat
database compression as a substitute for bandwidth-aware API design.

The final interface belongs in the existing `bughouse-chess` Next.js
application. Adapt the future API to its `ChessGame`, `MatchGame`, numeric game
id, UUID partner id, and player models. Reuse its board and replay components
where appropriate. The frozen Vite frontend is a behavior/reference source,
not the intended second production application.

The local prototype should be configuration-gated and point to localhost. It is
not a production deployment and should not require the full corpus: begin with
the deterministic representative artifact, validate prefetch behavior, and swap
in the full local artifact only after the streaming-writer gates pass.

Preserve the AGPL attribution and corresponding-source obligations when the
modified explorer is made available over a network. Keep the README's link to
the original Oh-My-Lands work and retain Git history.

## 3 August 2026 vertical-slice checkpoint

Workstream C's representation and bounded-memory implementation are now
demonstrated on repeated 91,911- and 186,009-game inputs. The packed v2 writer
projects about 2.58 GB at full scale and stayed below 72 MB observed peak RSS.
Compact per-game records reduced total representative bytes by about 26%.
Deterministic hashes, validation, immutable versioning, publication, rollback,
short-checkmate retention, internal endings, exact prefixes, and sorted seat
postings remain intact.

Workstream D's local service and comparison are implemented. The measured
adaptive default is 500 nodes rather than the initial 2,000-node hypothesis;
the 256 KiB default byte target and 4,000-node/512 KiB hard caps remain.
Representative root P99 stayed below 10 ms. Adaptive depth five used two
requests on the popular trace, versus seven per-move requests, while using
about half the bytes of fixed depth five. A corrected browser-policy simulation
that requires complete move lists measured those as two foreground requests
and zero idle refills; the earlier edge-presence-only comparison was
insufficient to detect partial visited branches.

Workstream E's local Next.js route, accessible sidebar link, one-board replay,
filters, bounded LRU, frontier refill, lazy games, and instrumentation are
implemented behind a production-disabled local flag. It remains a separate
page and did not change the two-board viewer.

The next gates, in order, are:

1. obtain a credible physical-write measurement for the streaming build;
2. complete the remaining real-browser filter, back-forward, and stale-request
   cancellation matrix now that loopback bootstrap and cached navigation pass;
3. only then decide whether the full checked local artifact is authorized; and
4. defer hosted API/CDN/authentication decisions until full-local query and UX
   evidence exists.

No full build or deployment occurred at this checkpoint.
