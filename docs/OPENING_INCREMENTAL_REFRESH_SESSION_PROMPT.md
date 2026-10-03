# Execute the September Opening Explorer update and incremental-builder migration

Execute this work through a validated local September 2026 opening release
candidate and a proven, repeatable incremental workflow. Do not stop at another
analysis or implementation plan. I authorize local implementation, bounded
workflow repairs, tests, long-running checked-snapshot bootstrap/reference
builds, incremental updates, deterministic exports, local frontend/service
verification, and offline transport preparation. External uploads, hosting
mutations, paid resources, deployment, production cutover, deletion of retained
data/artifacts, commits and pushes remain separately authorized actions.

Work in the same local checkouts:

- `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer`
- `/Users/aronteh/Desktop/Coding_Adventures/bughouse/bughouse-chess`

Start with applicable repository/ancestor instructions, then read:

1. `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer/docs/OPENING_INCREMENTAL_REFRESH_HANDOFF_2026-10-03.md`
2. `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer/docs/README.md`
3. `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer/docs/OPENING_INCREMENTAL_REFRESH_ANALYSIS_2026-10-03.md`
4. `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer/docs/OPENING_POSITION_GRAPH_REFACTOR_2026-09-01.md`
5. `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer/docs/PACKED_POSITION_GRAPH_V2_RESULT_2026-09-03.md`
6. `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer/docs/MONTHLY_DATA_AND_PLAYER_INSIGHTS_RESULT_2026-10-02.md`
7. `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer/docs/MONTHLY_FULL_ARTIFACT_VERCEL_RELEASE_RUNBOOK.md`
8. `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer/docs/BACKUP_RECOVERY.md` and `docs/PLATFORM_ARCHITECTURE.md` in the same backend checkout.

Read supplementary documents and current code/tests as directed by the handoff.
Treat old prefix-trie prompts and completed release documents as historical
context, not pending tasks or the current graph contract.

## Preflight and inputs

Inspect both working trees and all applicable instructions. Preserve existing
uncommitted/untracked analysis files listed in the handoff and unrelated changes;
do not reset, clean, stash away, or commit them to simplify your work. Recheck
disk/RAM, source integrity/checksums, current outputs, owned processes, and any
active/interrupted opening build or generation. Monitor/resume exact-source
work where appropriate rather than starting duplicates. Do not stop other
workers or tmux sessions without authorization.

Use these complete immutable sources, opened read-only:

- August: `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer/snapshots/monthly-20260901/crawler-through-2026-08.db`, SHA-256 `262b4cfc356a81b8dde88d4f6db863f155f8e8c5df1f14284fc8acb043828228`.
- Target: `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer/snapshots/monthly-20261002/crawler-through-2026-09.db`, SHA-256 `241f5e8dc353d42c751382223c386fa8fc495b8b792ada52920006695f2404eb`.

Do not open or depend on `data/crawler.db`, start Chess.com acquisition, or rerun
the completed Player Insights refresh. Do not build from diagnostic subset
databases. Preserve the complete target corpus, including historical backfills
and partial October; the period label is not an end-time filter. Do not substitute
a newer snapshot without a substantive decision from me.

Retain all previous snapshots/artifacts/checkpoints. Select and record fresh
date/retry labels before writing output. Account for simultaneous checkpoints,
full reference staging, exports, transport copies and rollback in peak-disk
preflight. Do not impose an artificial 12-hour stop: the one-time migration and
full correctness oracles can take longer than future monthly updates.

## Implement the durable incremental builder

Use the support/owner design and algorithm in the accepted analysis as the
starting architecture. Keep `packed-position-graph-v2` for serving. Defer a
segmented format, wholesale replay caching, hosting migration, and collector
change-journal work unless measured evidence establishes a necessary bounded
change. Routine implementation choices are yours; explain material changes.

Factor and instrument admission, replay, complete placement discovery,
materialized contributions, canonical export, repack, and verification. Preserve
the full builder as a correctness route that does not consume the incremental
checkpoint. Prove unchanged full-build outputs before scaling refactoring.

Implement:

- A normalized UUID/revision ledger with stable internal game keys, source
  order, admission/replay outcomes, complete adapter-field fingerprints,
  metadata, and recoverable previous move revisions.
- Complete distinct-game placement support and singleton ownership, including
  omitted tails. The old staging/shared files do not contain that missing data.
- Stable materialized position/state/edge/end contributions and username
  postings, with existing collision and replay invariants.
- Durable versioned generations and explicit bootstrap/update/resume/export/
  verify commands. Pin input checksums and semantic/engine versions. Keep the
  parent generation valid and fail closed on incompatible or incomplete state.
- Final-batch support changes and promotion/demotion owner repair. Replace old
  contributions atomically/idempotently. Updating a frontier must not add a
  second placement contribution for the same game. Maintain the sole owner even
  when a correction leaves support numerically unchanged, and exclude orphaned
  materialized objects from export.
- Metadata-only corrections, old/new player postings, outcome changes and
  admission transitions. Do not infer unchanged participants from an unchanged
  raw game hash. Preserve true endings and one contribution per distinct game
  per object despite repetitions, transpositions and cycles.
- Canonical export matching the full builder's target-source ordering, IDs,
  ordinals, offsets, dictionaries and dataset fingerprint. Internal stable keys
  are not public export IDs.

Add behavior-first fixtures for additions/deletions, move/result/rating/name/
source corrections, admission changes, hidden-singleton promotion, demotion,
owner replacement, long transposition bridges, cycles, repetition, real endings,
zero-support pruning and malformed-game atomic exclusion. Compare incremental
and full public semantics and canonical components. Test one batch versus split
or reordered batches, multi-month updates, no-op retry, and interruption/resume
at every durable stage. A checkpoint mismatch must not be silently repaired by
using the live database or accepting inconsistent counts.

## Execute and prove the actual update

After fixtures and representative parity pass, bootstrap an August checkpoint
from the checked full source, then apply the actual September target delta.
Reuse validated old materialized staging only in a new checkpoint copy and only
after exact source/artifact validation. Recover complete singleton ownership
through discovery; do not mutate the retained old files. A September-only
bootstrap does not replace proof of the August-to-September temporal update.

Preserve the current first-migration dual-full-build gate: produce independent
full September references A and B with the established builder and v2 repacker,
and a separate incremental September comparison output. Require the incremental
output to match both complete target references. Reuse completed exact-source
oracles after validation; do not start a third full target-reference build. A is
the sole release candidate, B the immutable oracle, and the incremental output
local comparison evidence. Shared checkpoint ancestry alone does not establish
independent correctness.

Reconcile the observed source delta: 196,852 new UUIDs, 151,497 new replayable
games, 64,166 existing accepted metadata changes, no deleted UUIDs or existing
move/admission changes, and the 21 unchanged prior replay exclusions. Expected
target opening count is 6,899,477. Check the actual result rather than forcing
these numbers. Enumerate the complete threshold-affected set; the analysis's
46,971 old extensions and 291 newly reached endings are only lower bounds.

Require complete source and artifact integrity, component SHA-256/size parity,
semantic counts and versions, all source-game metadata parity, and representative
filtered/unfiltered query parity. Record every inclusion/exclusion and failure
outcome. Measure bootstrap/support-table size, replayed and repaired games,
discovery/update/export/repack/verification times, peak RAM/disk, artifact bytes,
startup/query latency and the next-month incremental path. Never report scan-only
timings as a complete exporter or monthly-build benchmark.

## Local release readiness and operational integration

Resolve the verified tooling gaps in the handoff with bounded tests: graph-aware
roots/state-aware HTTP oracle, compatible graph benchmarks/lifecycle tests,
run-aware recovery checks, exact allowlists in all three transport/stage/runtime
modules, and the documented 30-second versus source-default 45-second proxy
timeout discrepancy. Do not change limits or broaden allowlists implicitly.
Retain old rollback identifiers; permit the exact A name and reject B/comparison
outputs. Do not introduce external writes while repairing local code.

Run the required backend and frontend tests, lint/type checks, production build,
artifact/lifecycle/startup/HTTP/concurrency/cancellation/filter/ending/drop/game
reference/ETag/hard-cap checks, and desktop/mobile browser matrix against a local
service using the exact new candidate. Exercise renamed-player postings,
transposition navigation, meaningful deep links and true endings. Preserve the
bounded proxy, server-only credentials, viewer and cache-version behavior; no
database, packed artifact, raw corpus or full postings download to the browser.

Prepare deterministic transport locally under a fresh external temporary
directory, validate exact offline reconstruction and interrupted-retry behavior,
and create a concrete sanitized release packet with identities, sizes, current
hosting eligibility/CLI/configuration checks, exact deployment and rollback
steps, and approvals still needed. Present this packet before any external
upload or environment mutation. Do not upload, rehearse remotely, deploy or
promote without the explicit applicable approval.

Update the operator runbook with tested commands, checkpoint recovery, policy
invalidation, resource measurements, verification and rollback. Any future
replacement of routine dual-full replay must be explicit and supported by the
first-migration parity/recovery evidence; preserve the existing gate while
creating that evidence. Update README counts/sizes from actual measured outputs,
clearly distinguishing local candidate from the currently served production
dataset. Preserve historical results and completed Player Insights projections.

Write a new dated implementation/result record and link it from the documentation
map. Include exact source/checkpoint/artifact identities, source and complete
affected-game deltas, corrections/exclusions/failures, deterministic parity,
raw/component/gzip where meaningful/transport sizes, checksums, phase timings,
tests, browser evidence, interruption recovery and rollback/release actions.
Maintain a durable progress ledger with exact resume commands as long work
proceeds so another interruption does not require restarting the analysis.

Persist through long-running local work and provide concise progress updates.
Do not stop after a partial prototype or first passing test. Stop only for a
substantive blocker or at the completed local release-readiness boundary where
external authorization is required. Finish with the measured outcome, links to
the new result/runbook, remaining release approvals, and changes ready for my
review and commit. Do not commit or push.
