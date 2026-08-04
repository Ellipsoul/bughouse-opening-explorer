# Full opening-tree scale-up plan — 3 August 2026

## 4 August 2026 status

Workstreams A–D are complete locally. The first-load phases are measured, the
restored input and recovery headroom passed preflight, two deterministic full
artifacts were built and validated, local service/browser/lifecycle tests
passed, and current official hosting limits were refreshed. The measured
result and commands are in
[`FULL_OPENING_TREE_SCALE_UP_RESULT_2026-08-04.md`](FULL_OPENING_TREE_SCALE_UP_RESULT_2026-08-04.md).

Workstream E remains approval-gated. The recommendation is a protected,
preview-only Vercel Large Functions trial; no full upload, paid provisioning,
production configuration, promotion, commit, or push has occurred.

## Objective

Scale the settled exact-prefix opening explorer from the validated 91,911-game
representative artifact to the full accepted-game corpus, first through a
reproducible local build and local browser trial, then through a separately
approved production publication.

The first task is not the full build. It is to explain the current first-load
delay with measurements and determine which work is bounded per request and
which work grows with artifact size. The full local build may proceed only
after input, recovery, disk, memory, and timing preflight gates pass. Production
upload remains a later approval gate informed by the local evidence and current
provider limits.

## Current checkpoint

- The retained representative contains 91,911 accepted games and is
  `packed-prefix-interval-v2`.
- It is immutable, validated, versioned, approximately 36.8 MB, and served by a
  bounded memory-mapped reader.
- The client first requests metadata and then requests one neighborhood for the
  root or requested deep-link node. That neighborhood remains capped at the
  depth-five target, 500 nodes/256 KiB defaults, and 4,000 nodes/512 KiB hard
  limits. The browser never downloads the packed artifact.
- Local use requires two processes: the Python reader on loopback port 8765 and
  the Next.js application on port 3000.
- The production representative uses a checksum-validated bundled-artifact
  Python Vercel Function behind the server-only same-origin Next.js proxy.
- The page, sidebar link, and proxy are now always present in local, Preview,
  and Production builds. Availability flags have been retired; service-origin,
  credential, path, timeout, and response-budget protections remain.
- The retained full-artifact projection is approximately 2.58 GB, but this is
  a projection rather than a measured final build. The final size, file mix,
  startup cost, and provider fit must be measured.

## First-load question to answer

Measure the following stages separately rather than treating page load as one
number:

1. Next.js route JavaScript, hydration, and board-component initialization.
2. Browser-to-Next proxy time for `/api/meta`.
3. Proxy-to-reader connection and any hosted authentication overhead.
4. Cold process import and application construction.
5. Manifest parsing and per-file checksum validation.
6. Packed-index construction, file opens, and memory-map creation.
7. Metadata serialization and transfer.
8. The sequential root/deep-link neighborhood query, bounded traversal,
   serialization, compression, and transfer.
9. Client cache merge, path reconstruction, board replay, and first useful
   paint.

Record whether each phase is approximately constant, proportional to file
count, proportional to artifact bytes, proportional to selected postings, or
bounded by the existing node/byte budgets. In particular, test the hypothesis
that checksum validation is linear in artifact bytes while memory-map creation
and bounded unfiltered neighborhood reads need not make the artifact resident
in memory.

## Workstream A — instrument the representative baseline

- Add explicit startup phase timings without logging paths, payloads,
  usernames, tokens, or raw game data.
- Separate process start, manifest/checksum validation, reader construction,
  first metadata, first neighborhood, warm metadata, and warm neighborhood.
- Capture browser navigation timing for cold page, warm page, HTTP cache hit,
  and already-warm reader.
- Run cold-process repetitions rather than extrapolating from one start.
- Measure wall time, CPU time, bytes read, peak RSS, mapped virtual bytes,
  resident bytes, page faults, open files, response bytes, and P50/P95/P99.
- Preserve the existing representative artifact as the correctness and
  performance baseline.

## Workstream B — authorize and build the full local artifact safely

Before building:

- Never read from, lock, copy implicitly from, or operationally depend on
  `data/crawler.db`.
- Use only an explicit separately restored, SQLite-validated snapshot with a
  recorded SHA-256 and immutable path. If no suitable checked snapshot exists,
  stop and request direction rather than substituting the live database.
- Confirm free space for the source snapshot, final immutable artifact,
  temporary writer state, a second validation copy where required, and rollback
  headroom. Do not rely on the 2.58 GB projection alone.
- Re-run SQLite integrity/invariant checks on the separate snapshot and record
  the accepted-game count used by the adapter.
- Run a smaller deterministic streaming-writer rehearsal if any writer or
  format code has changed since the representative checkpoint.
- Keep the representative artifact untouched and available for comparison and
  rollback.

Build the full version to a new explicit artifact directory. Record phase
times, progress, temporary and final bytes, write amplification, peak RSS, CPU,
errors, manifest contents, every component checksum, and deterministic rebuild
evidence. Validate semantics against the shared corpus before publication.

## Workstream C — full-tree local service and browser trial

- Start the existing reader against the new full artifact only after validation
  succeeds.
- Compare representative and full cold readiness, first metadata, first root
  neighborhood, warm navigation, filters, support-one, internal endings, drops,
  direct deep links, and stale-version handling.
- Verify the same response budgets and deterministic ETags remain enforced.
- Measure concurrent users, process restarts, mapped/resident memory, disk
  reads, and browser request/byte counts.
- Demonstrate local correction, version switch, rollback to the representative,
  and removal without mutating either immutable artifact.
- Investigate any latency regression before changing response budgets,
  terminal policy, node identity, or client cache behavior.

## Workstream D — current full-scale hosting decision

Refresh official provider documentation and live account/project limits at the
time of the next session. Re-evaluate at least:

1. Vercel Large Functions beta or its current successor with the immutable
   artifact bundled.
2. A Vercel Function plus immutable object storage only if cold materialization,
   local disk capacity, validation, and egress are viable for the measured
   artifact.
3. A small external container running the existing reader as the comparison
   control.
4. A database projection only if it preserves exact-prefix identity and proves
   a material operational advantage over the packed-reader oracle.

For each, record dated official limits, deployment size, cold start, duration,
memory, local disk, concurrency, regions, bandwidth/egress, monthly cost,
correction, rollback, deletion, export, lock-in, and AGPL corresponding-source
requirements. Do not assume the previously documented 500 MB Function path or
current beta behavior is unchanged.

## Workstream E — staged production publication

Do not upload the full artifact, provision a paid resource, change Vercel
environment configuration, or deploy production until the measured local
results and current hosting options have been presented and explicit approval
has been obtained.

After approval:

1. stage a new immutable full version without replacing the representative;
2. validate checksum/readiness and run service smoke/concurrency tests;
3. point a non-production web boundary at it and run the shared browser corpus;
4. compare cold and warm production behavior with the local evidence;
5. obtain explicit promotion approval;
6. switch the production service version without changing the existing `/`
   viewer;
7. retain the representative deployment as immediate rollback; and
8. demonstrate correction, rollback, and complete removal.

## Shared benchmark corpus

Use identical representative and full traces:

- first cold page visit, warm page visit, cold reader, warm reader, and process
  restart;
- root and popular seven-position mainline;
- branch, backtrack, alternate branch, deep sparse path, and direct deep link;
- unfiltered, White, Black, exact-pair, support-one, and filter-change cases;
- internal endings, identical lines, retained short drop checkmate, and sole
  game source details;
- 1, 8, 32, and 64 bounded concurrent clients where the host permits;
- stale dataset, correction, rollback, missing service, corrupt artifact, and
  request cancellation; and
- cold browser, memory hit, immutable HTTP hit, and dataset-version cleanup.

Record P50/P95/P99 end-to-end and reader latency, time to first useful explorer
state, requests, compressed/uncompressed bytes, startup phase timings, CPU,
RSS, mapped/resident bytes, page faults, disk reads, errors, cache utilization,
and observed/projected cost.

## Definition of done

The next slice is complete only when:

- the representative first-load delay has a measured phase breakdown;
- the full artifact was built reproducibly from an explicit checked snapshot,
  or a concrete evidence-backed blocker is recorded;
- full local semantic and performance results are compared with the
  representative under the same budgets;
- a current full-scale hosting decision is made from official limits and live
  measurements;
- any production publication was separately approved, staged, validated,
  benchmarked, and shown to roll back and remove cleanly;
- the normal two-board viewer remains unchanged; and
- no live crawler database, Chess.com traffic, browser artifact transfer,
  unbounded username export, or unauthorized production/cost action occurred.
