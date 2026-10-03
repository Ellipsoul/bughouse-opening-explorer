# Incremental Opening Explorer refresh — analysis and implementation plan

> Historical migration material: completed on 3 October 2026. For future months,
> use [the current runbook](OPENING_INCREMENTAL_RUNBOOK.md) and
> [completed result](OPENING_INCREMENTAL_RESULT_2026-10-03.md). Do not rerun this migration task.

## Decision proposed

Build a durable local incremental analysis store and continue publishing complete
immutable `packed-position-graph-v2` artifacts. Preserve the current placement,
state, distinct-game support, terminal, filtering, and rollback contracts.

The first implementation should retain **complete placement support counts and
singleton owners**, rather than cache every full state/edge replay. Replay new
or move-corrected games and the older games affected by a shared-position
threshold change. Retained checked snapshots supply those older move sequences.
Full replay caching remains a measured follow-up if affected-game replay proves
expensive. A segmented serving format is deferred until export or transport
measurements justify its added query and correction complexity.

This document records completed analysis, not an implemented incremental builder
or a release. The current dual-full-build release procedure still applies.

## Inputs and completed checks

Both working trees were clean at the start. Backend revision:
`4b1c7cd91c935ca0bb938601412a4d83cd6f2b98`; frontend revision:
`32b8ea7daf8d61c5bec165971ac4f497e35d6116`. Applicable repository/ancestor
instruction files were checked; no `AGENTS.md` was present. The documentation
map, monthly runbooks, latest monthly result, graph design, architecture,
roadmap, adapter, builders, repacker, reader, and retained staging schema were
examined. Available disk space was 755 GiB.

All source reads used explicit read-only, immutable connections. Both source
hashes were recomputed and matched their checked result records:

| Input | SHA-256 |
| --- | --- |
| `snapshots/monthly-20260901/crawler-through-2026-08.db` | `262b4cfc356a81b8dde88d4f6db863f155f8e8c5df1f14284fc8acb043828228` |
| `snapshots/monthly-20261002/crawler-through-2026-09.db` | `241f5e8dc353d42c751382223c386fa8fc495b8b792ada52920006695f2404eb` |

The August reference is `full-position-graph-through-202608-v1`, build/dataset
`68a97678c3df093d243473e0844b373d669ac335`, with 6,747,980 replayable games.
Its component checksums and structural validation passed again. All 73,473
singleton memberships used by the impact probe matched the checked packed
reference's placement identity, support, and game ordinal. Its packed v2 serving
representation is retained alongside it. Historical
snapshots, artifacts, and result documents were preserved.

The reusable diagnostic command is:

```bash
PYTHONPATH=. .venv/bin/python scripts/analyze_opening_snapshot_delta.py \
  snapshots/monthly-20260901/crawler-through-2026-08.db \
  snapshots/monthly-20261002/crawler-through-2026-09.db \
  artifacts/opening-analysis/<fresh-analysis-label>/delta \
  --before-sha256 262b4cfc356a81b8dde88d4f6db863f155f8e8c5df1f14284fc8acb043828228 \
  --after-sha256 241f5e8dc353d42c751382223c386fa8fc495b8b792ada52920006695f2404eb
```

This command produces aggregate evidence and adapter-compatible diagnostic
subsets. The subsets contain only candidate boards and are **not complete source
snapshots or release inputs**. Existing output directories and checksum
mismatches are rejected; failed diagnostic outputs require a fresh label.

## Exact source delta

| Measure | Count |
| --- | ---: |
| Previous stored boards | 8,487,878 |
| Current stored boards | 8,684,730 |
| New board UUIDs | 196,852 |
| Deleted board UUIDs | 0 |
| Existing boards with relevant source/participant changes | 82,680 |
| Existing adapter-accepted boards with metadata changes | 64,166 |
| Existing changed boards still skipped as empty TCN | 10,197 |
| Existing changed boards still skipped as short non-checkmates | 8,317 |
| Existing TCN, rules, or initial-setup changes | 0 |
| Existing adapter admission transitions | 0 |
| Existing rowid changes | 0 |
| New adapter-accepted and successfully replayed games | 151,497 |
| New empty-TCN skips | 27,806 |
| New short-non-checkmate skips | 17,549 |

The accepted metadata changes include 32,126 white-username and 32,198
black-username changes, across 60 distinct old/new username replacement pairs.
Some games changed both names. Six accepted games changed source/provenance;
four white and two black raw result strings changed. No accepted ratings changed,
and no existing game changed its win/draw/loss bucket. The new artifact must
replace the affected username postings and browser metadata, even though those
games need no topology replay for their metadata correction.

The full comparison checks participant identities, ratings, results, and global
username changes independently of the game's raw content hash. In these actual
inputs all 82,680 candidate existing boards also changed their content hash;
the tool's fixtures demonstrate why that coincidence cannot become a future
assumption.

| New boards by UTC game end month | Stored | Adapter accepted |
| --- | ---: | ---: |
| History through August 2026 | 75,137 | 54,683 |
| September 2026 | 116,062 | 92,562 |
| Mutable October 2026 | 5,653 | 4,252 |
| Total | 196,852 | 151,497 |

The new accepted set spans October 2016 through October 2026. This is a corpus
delta including lifetime backfills and corrections, rather than a September-only
append. The new accepted games are 2.245% of the previous replayable corpus.
They contain 7,368,094 plies and have zero graph replay errors.

With unchanged admission and replay inputs for every existing board, the
expected next graph game count is **6,899,477**. This reconciles with the current
Player Insights analyzed count. It is a delta-derived expectation, not a count
from a newly built opening artifact; position/state/edge totals remain unknown.

## Why appending the new paths is insufficient

The current policy is `last-shared-placement-plus-one-or-game-end-v1`.
Sharedness means at least two distinct accepted games reach a piece placement;
rules-state identity additionally includes side, castling rights, and en passant.
Repetition within one game contributes once to support.

A new game can promote a formerly singleton position to shared, extending an
older game's materialized path. A correction or removal can demote a position
and shorten the remaining game's path. Both changes can alter real-ending
membership. Frontier repair must use the final whole-batch shared set, so results
do not depend on the order in which changes happen to be processed.

The diagnostic replay measured:

| Observed impact | Count |
| --- | ---: |
| Distinct placements visited by new games | 5,577,554 |
| Those absent from the old shared-placement set | 5,127,756 |
| Old materialized singleton placements reached by new games | 73,473 |
| Older games associated with those singleton placements | 65,625 |
| Guaranteed newly shared placements, lower bound | 83,530 |
| Older games requiring longer paths, lower bound | 46,971 |
| Additional old-game edge occurrences, lower bound | 48,637 |
| Previously omitted real endings now reached, lower bound | 291 |

These are **lower bounds**. The old discovery pass discarded singleton facts
beyond materialized tails. New games may also reach those hidden positions, but
their older owners cannot be enumerated from the retained graph. No claim is
made that 65,625 is the complete affected-game set.

The retained 22,291,058,688-byte SQLite staging store contains published
positions/states/edges, their game memberships, endings, postings, and dense ID
maps. Its discovery file contains 5,985,342 shared keys and has SHA-256
`2a0c9a1317f4901bd4b44935754f54127a30effdbfca78f97e7afd00a7c42aef`.
It lacks hidden singleton owners and full paths. The staging writer also uses
`journal_mode=OFF` and `synchronous=OFF`; the retained file is not a durable
incremental checkpoint. Preserve it as diagnostic/reuse evidence and bootstrap
new checkpoints separately.

The legacy `bughouse_explorer/indexer.py` does implement new-UUID anti-join
indexing. It uses the former schema, a depth limit, different node identity,
and skips existing UUIDs. Its batching/journal ideas are useful references, but
its admission, correction, and graph semantics cannot replace the current
builder.

## Measured cost and remaining uncertainty

| Operation | Observed wall time |
| --- | ---: |
| Complete source/participant delta audit, including both source hashes | 105.37 s; repeat 119.97 s |
| Full state/edge replay of all 151,497 added games, plus placement counting | 188.58 s |
| Lookup of known old singleton memberships | 24.58 s |
| Replay/check of 65,625 potentially affected old games | 87.53 s |
| Read-only scan of all 361,216,254 existing membership entries | 238.49 s |
| Historical complete August semantic build | 21,092.64 s (5 h 51 m 33 s) |
| Historical v1-to-v2 repack | 105.94 s |

The four export-query scans matched the August artifact's total membership
count. Their query plans scan dense ID maps and use indexed membership lookups;
they did not require a temporary ORDER BY sort in this environment. The replay
probe peaked at 2,541,879,296 bytes RSS; the scan at 375,291,904 bytes.

These are local diagnostic timings with warmed/mixed caches and some concurrent
analysis. The membership scan excludes ID regeneration, other export queries,
aggregation, writing, hashing, repacking, and validation. The replay measurement
excludes durable contribution updates and complete frontier repair. They are
not an end-to-end incremental-build benchmark or a monthly runtime guarantee.

The evidence supports avoiding routine whole-corpus replay. It also shows that
complete export remains proportional to published facts. Instrument discovery,
replay, contribution writes, ID assignment, export, repack, and verification
separately before setting a monthly runtime target. A full replay cache or a
segmented format should earn its storage/query complexity through measurements.

## Proposed durable store and update algorithm

Keep the local analysis store separate from the immutable serving artifact:

```text
checked previous + current snapshots
    -> normalized source delta
    -> complete placement support / singleton-owner ledger
    -> replay changed games and threshold-affected older owners
    -> update materialized graph facts and player postings
    -> deterministic complete v2 export
    -> validation and existing release procedure
```

The durable store needs:

1. A game ledger keyed by UUID, with stable internal game keys, normalized
   adapter fields, source/replay/metadata fingerprints, admission or terminal
   replay outcome, source order, and provenance. Internal keys must be separate
   from export ordinals.
2. A **complete** placement table: stable placement key, distinct-game support,
   and sole game key when support is one. It includes hidden singleton tails.
   Complete placement-to-game postings are not required for every hidden tail.
3. Materialized position/state/edge/end memberships keyed by stable identities
   and internal game keys, plus username postings. Preserve existing collision
   checks and `(state, token) -> child` replay invariants.
4. Checkpoint provenance: input checksums, parent generation, adapter/replay/
   engine/identity/terminal policy versions, durable job progress, and completion
   validation. Keep a checked source reference or move sequence for every
   current game so correction subtraction is recoverable.

For a change batch:

- Replay only new games, changed move inputs, and games newly admitted. For
  removals or old move corrections, replay the prior revision from its retained
  source to obtain the old distinct placements and contributions.
- Compute final signed placement-support changes with one contribution per
  game per placement. Update singleton ownership even when a replacement leaves
  the final support count unchanged; support zero has no owner. Metadata-only
  changes do not alter those counts.
- A singleton becoming shared names its previous owner directly. A shared
  placement becoming singleton obtains its survivor from the previous shared
  graph memberships, excluding removed visits, or from the incoming revisions.
  Existing shared positions have complete membership coverage under the current
  terminal policy. Validate the survivor and final count before proceeding.
- Queue those owners once, replay their complete moves, and derive old/new
  materialization frontiers. Repairing an unchanged game's frontier must not
  count its placements as a second source contribution.
- Replace old materialized contributions rather than incrementing aggregate
  totals blindly. Correct result buckets and endings exactly; update metadata
  and remove old/add new username postings for renames. Remove unreferenced
  materialized objects, or exclude them from export, so shortened paths leave
  exactly the objects a full build would contain.
- Export in the same canonical source/game/key/edge order as the full builder.
  Reassign dense IDs, ordinals, offsets, and dictionaries at publication. This
  retains the current public v2 reader and allows complete byte comparison.

Use transactions and durable journaling for the new store. Work in a fresh
generation, retain its parent, resume only against the same target checksum and
policy, and mark a generation current after validation. An interrupted update
must not expose a partially corrected checkpoint. Incompatible replay/identity
or admission policy changes trigger an explicit rebuild/migration, not an
incremental guess.

## Implementation sequence and acceptance gates

1. **Factor and instrument the current builder.** Separate source admission,
   replay, placement discovery, materialized-fact updates, canonical export,
   and repack. Keep the full builder as the independent comparison route.
   First demonstrate byte-identical output from the refactoring on fixtures
   and the retained representative corpora.
2. **Add complete support/owner checkpointing.** Extend discovery to retain
   counts and singleton ownership instead of discarding singleton records.
   Add the versioned game ledger and durable generation/resume protocol.
   Bootstrap from a checked full source; the existing staging data can seed
   materialized facts after exact validation, but cannot fill hidden owners.
3. **Implement changes and frontier repair on fixtures.** Require parity with
   full builds for additions, deletions, move/result/rating/name/source
   corrections, admission transitions, promotion/demotion, repeated positions,
   cycles, shared transposition bridges, and real endings. Include changed
   participant fields without a changed raw hash.
4. **Prove determinism and recovery.** One batch, split batches, reordered
   application, retry after each durable stage, and multi-month updates must
   reach the same target graph. Fail closed on missing prior revisions,
   checksum/version mismatches, inconsistent owners, or duplicate membership.
5. **Bootstrap and validate at scale.** Measure the complete support-table size
   and exact affected-game set. Compare a next-snapshot incremental result with
   an independent full build: canonical component hashes, counts, every source
   metadata record, representative full query results/filters, capacity,
   latency, and peak disk/RSS. The initial bootstrap retains a corpus-sized
   cost; it should also produce the current serving candidate.
6. **Integrate the operator workflow after proof.** Add explicit bootstrap,
   update, resume, export, and verify commands with fresh output labels and a
   machine-readable ledger. Update the release runbook only after parity and
   interruption evidence. Preserve existing external release approvals and
   rollback artifacts.

An August checkpoint followed by the actual September delta is the strongest
first full-scale incremental comparison. Bootstrapping directly from September
can serve the current month, but requires a separate temporal comparison before
the monthly update path is established. Reusing validated August staging facts
may save materialization work; completing its owner ledger still requires a
full discovery replay. The time and storage of that bootstrap are unmeasured.

Two runs from the same checkpoint demonstrate reproducibility, not independent
correctness of the checkpoint. During rollout keep full-build parity; afterward
use independent change validation, exact cohort/count reconciliation, and
scheduled full audits under an explicitly revised runbook. The current two-full-
build gate is not waived by this analysis.

If complete export or package transport later dominates, evaluate immutable
base/delta segments with revisions, removals, exact membership unions, and
bounded segment counts plus compaction. Summing segment counts is not sufficient.
That design changes the serving reader and release tooling and is a separate
measured phase.

If the full snapshot comparison later becomes significant, evaluate an atomic
collector change journal with snapshot-bound watermarks. It must cover game,
participant, and player-username mutations, including every board affected by
an account rename. A game-only timestamp or raw-hash feed is insufficient.
Retain periodic complete snapshot comparisons to establish journal coverage.

## Evidence, verification, and boundaries

Local machine-readable evidence is retained under
`artifacts/opening-analysis/20261003/`:

- `delta/snapshot-delta.json` and `delta-r2/snapshot-delta.json`: independent
  reruns with matching corpus, field-change, classification, and month counts;
- `delta-r2/snapshot-delta.json`: accepted-field and result-bucket breakdown;
- `replay-impact.json`, `position-impact.db`, and `replay_probe.py`: new-game
  replay and lower-bound old-frontier evidence;
- `export-query-plans.json`, `export-scan.json`, and `export_scan_probe.py`:
  complete membership scan evidence and reproducible local probe source.
- `baseline-parity.json`: successful complete v1 artifact validation and parity
  of every singleton membership used by the impact probe.

The diagnostic scripts and databases under `artifacts/` are ignored local
evidence. The reusable snapshot-audit script and its tests are tracked for
review. The new graph contract fixture demonstrates that adding a second game
extends an older tail and that removing it restores the original graph bytes
under the same source fingerprint.

Backend verification: **261 tests passed**, including five audit-tool tests and
the new threshold-transition graph fixture. `git diff --check` passed. No
frontend application code/data changed, so frontend/browser release checks were
not repeated. They remain required when a real candidate is built and released.

No live crawler reads/writes, full-corpus packed opening artifact, upload, environment
mutation, deployment, commit, or push occurred. The existing serving dataset and
previous rollback inputs remain intact. The incremental builder, complete owner
ledger, final exporter benchmark, and next opening artifact are still to be
implemented/produced through the gates above.
