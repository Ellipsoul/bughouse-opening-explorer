# Opening Explorer incremental refresh — execution handoff

## Session objective and boundary

Implement and prove a durable incremental opening builder, apply the complete
August-to-September 2026 corpus delta, and prepare a fully validated immutable
September opening release candidate. Keep the public packed v2 format and the
current graph semantics. Complete local transport preparation and a concrete
release/rollback packet; external uploads and production actions require the
separate approvals in the release runbook.

The copy-ready task is
[`OPENING_INCREMENTAL_REFRESH_SESSION_PROMPT.md`](OPENING_INCREMENTAL_REFRESH_SESSION_PROMPT.md).
Use the same two local checkouts so the existing uncommitted analysis work is
available. This handoff does not authorize a commit, push, deployment, deletion,
paid resource, or production mutation.

## Essential documentation, in reading order

Read applicable repository instructions first, then:

| Document | Purpose |
| --- | --- |
| This handoff and [`README.md`](README.md) | Current state and navigation |
| [`OPENING_INCREMENTAL_REFRESH_ANALYSIS_2026-10-03.md`](OPENING_INCREMENTAL_REFRESH_ANALYSIS_2026-10-03.md) | Measured delta, lower-bound frontier impact, proposed support/owner ledger, algorithm, and implementation gates |
| [`OPENING_POSITION_GRAPH_REFACTOR_2026-09-01.md`](OPENING_POSITION_GRAPH_REFACTOR_2026-09-01.md) | Authoritative placement/state identity, transpositions, distinct-game counting, terminal policy, and current graph contract |
| [`PACKED_POSITION_GRAPH_V2_RESULT_2026-09-03.md`](PACKED_POSITION_GRAPH_V2_RESULT_2026-09-03.md) | Current serving layout, exact capacity gates, parity and performance reference |
| [`MONTHLY_DATA_AND_PLAYER_INSIGHTS_RESULT_2026-10-02.md`](MONTHLY_DATA_AND_PLAYER_INSIGHTS_RESULT_2026-10-02.md) | Completed acquisition, lifetime backfills, closure, checked target source, exclusions and Player Insights reconciliation |
| [`MONTHLY_FULL_ARTIFACT_VERCEL_RELEASE_RUNBOOK.md`](MONTHLY_FULL_ARTIFACT_VERCEL_RELEASE_RUNBOOK.md) | Full-build oracle gate, allowlists, local verification, transport, release approvals, and rollback |
| [`BACKUP_RECOVERY.md`](BACKUP_RECOVERY.md) and [`PLATFORM_ARCHITECTURE.md`](PLATFORM_ARCHITECTURE.md) | Source integrity, immutable publication, and recoverability boundaries |

Consult `CRAWLER.md` and `MONTHLY_DATA_AND_PLAYER_INSIGHTS_RUNBOOK.md` for source
policy; no new acquisition is needed for this slice. Consult `PLATFORM_ROADMAP.md`
for legacy indexer context. Use the latest applicable release/result documents
for HTTP, concurrency, attestation, browser and rollback details. Read frontend
instructions/package scripts if editing or verifying that checkout.

The older scale-up and preview prompts describe prefix-trie artifacts or
completed releases. Do not execute their historical tasks or adopt their
obsolete node-identity assumptions. The September graph specification and v2
implementation govern this slice.

## Current local checkpoint

Backend checkout:
`/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer`.
Frontend checkout:
`/Users/aronteh/Desktop/Coding_Adventures/bughouse/bughouse-chess`.

Last checked backend HEAD: `4b1c7cd91c935ca0bb938601412a4d83cd6f2b98`.
Frontend HEAD: `32b8ea7daf8d61c5bec165971ac4f497e35d6116`.
Recheck current branches, remotes, instructions, disk, RAM, processes and output
directories before starting. Do not replace or stop someone else's work.

Existing backend uncommitted work is the accepted analysis baseline:

- `docs/OPENING_INCREMENTAL_REFRESH_ANALYSIS_2026-10-03.md`;
- `scripts/analyze_opening_snapshot_delta.py`;
- `tests/test_opening_snapshot_delta.py`;
- the threshold-addition/removal fixture in
  `tests/test_opening_position_graph_streaming.py`;
- analysis links in `docs/README.md` and the full-artifact release runbook;
- this handoff, its session prompt, and their documentation-map links.

Some new files are untracked. Preserve them; do not assume a fresh worktree from
the remote contains them. The frontend was clean. The incremental builder is
**not implemented**, and no new full opening artifact exists from this analysis.
Baseline backend tests: **261 passed**; whitespace checks passed. Available disk
was approximately 755 GiB; that is a dated observation, not a current budget.

## Frozen source and reference identities

All paths below are relative to the backend checkout.

| Role | Path | SHA-256 / identity |
| --- | --- | --- |
| August source | `snapshots/monthly-20260901/crawler-through-2026-08.db` | SHA-256 `262b4cfc356a81b8dde88d4f6db863f155f8e8c5df1f14284fc8acb043828228`; 8,487,878 stored boards |
| September target source | `snapshots/monthly-20261002/crawler-through-2026-09.db` | SHA-256 `241f5e8dc353d42c751382223c386fa8fc495b8b792ada52920006695f2404eb`; 16,067,272,704 bytes; 8,684,730 stored boards |
| August semantic reference | `artifacts/opening/full-position-graph-through-202608-v1` | Dataset/build `68a97678c3df093d243473e0844b373d669ac335`; 6,747,980 games |
| August serving reference | `artifacts/opening/full-position-graph-through-202608-v2` | Same dataset/build; 3,386,499,197 total bytes including manifest |
| August materialized staging | `artifacts/opening-build-temp/full-position-graph-through-202608-v1/graph-staging/opening-position-graph.sqlite3` | 22,291,058,688 bytes; partial replay coverage; durability disabled during original build |
| August shared keys | `artifacts/opening-build-temp/full-position-graph-through-202608-v1/shared-position-discovery/shared-position-keys.bin` | 5,985,342 keys; SHA-256 `2a0c9a1317f4901bd4b44935754f54127a30effdbfca78f97e7afd00a7c42aef` |

Source hashes were recomputed during analysis; the August v1 reference passed
complete checksum/structural validation. Do not use the mutable live crawler or
the diagnostic candidate-subset databases as build inputs. The target source
contains September, partial October, and historical backfills; do not impose a
September end-time filter or replace it with a later monthly snapshot silently.

Local ignored evidence is in `artifacts/opening-analysis/20261003/`:
`delta/snapshot-delta.json`, `delta-r2/snapshot-delta.json`,
`delta/metadata-changes.json`, `replay-impact.json`, `position-impact.db`,
`export-query-plans.json`, `export-scan.json`, and `baseline-parity.json`.
The aggregate result and full interpretation are recorded in the reviewable
analysis document; keep it usable if local ignored evidence is unavailable.
The two replay/export probe sources are also retained in this local directory.

## Known semantic and performance facts

- New raw UUIDs: 196,852; newly replayable games: 151,497; deleted UUIDs: zero.
- Existing accepted metadata changes: 64,166, predominantly username changes;
  no existing move changes or admission transitions; no result-bucket changes.
- New replay errors: zero. Expected next opening game count: **6,899,477**;
  the previous 21 replay exclusions remain to be explicitly reconciled.
- At least 46,971 older paths extend, at least 291 previously omitted endings
  become reachable. The complete affected set is unknown until hidden
  singleton ownership is recovered.
- New-game replay took 188.58 s; checking 65,625 known potentially affected old
  games took 87.53 s. The full existing membership scan took 238.49 s. These
  exclude durable updates and complete export, and are not runtime promises.

The retained staging/shared files cannot supply hidden singleton owners. A
one-time full discovery/bootstrap is necessary. Prefer a complete placement
count + sole-owner ledger, stable UUID/game keys, materialized memberships, and
versioned generations. Replay only new/corrected games and owners affected by
final-batch threshold crossings. Retain exact source revisions for subtraction
and recovery. Full replay caching and segmented serving remain deferred.

## First-migration oracle policy and output naming

An August checkpoint followed by the exact September delta is required to prove
the actual temporal update. A direct September bootstrap alone does not prove
incremental behavior. Reuse validated August materialized facts if helpful, but
never mutate the existing staging or artifacts, and rebuild missing complete
support/owner coverage from the checked source.

The current runbook requires two independent full September semantic builds and
v2 repacks, A and B. Retain that gate for this first migration and compare the
separately produced incremental September output with **both**. This requires
two full target-reference builds, not a third full target-reference build.
The August bootstrap is additional one-time work. A remains the sole external
release candidate; B is an immutable independent oracle; the incremental
comparison output is local evidence. Resume already valid exact-source builds
rather than creating duplicates.

Use a fresh date/retry label in all checkpoint, temporary, result, and artifact
paths. Suggested families are `opening-incremental-<label>/` for checkpoints,
`full-position-graph-through-202609-<label>-v1-a` / `-v2-a` and corresponding
`-b` for references, and `incremental-position-graph-through-202609-<label>-v1`
/ `-v2` for the comparison. Record exact chosen names before bounded allowlist
updates. The period remains September regardless of execution date.

After full-scale parity and recovery proof, document a concrete future monthly
protocol that replaces routine corpus replay with verified updates. Any change
to the operative release verification gate must be explicit in the new result
and runbook, with its evidence; do not silently weaken the current gate during
the initial migration. First-migration time can exceed the previous dual-build
estimate; there is no user-imposed 12-hour cutoff.

## Release-tooling gaps to verify and repair within scope

These were inspected during handoff preparation; recheck before modifying:

- Exact-name allowlisting covers `vercel_transport.py`, `vercel_stage.py`, and
  `vercel_hosted.py`, not just the latter two listed in the older runbook text.
  Permit only the exact A name while preserving the rollback policy; reject B
  and the incremental comparison artifact.
- `scripts/validate_hosted_opening_oracle.py` assumes root zero, prefix-tree
  reader methods, and lacks graph-state-aware queries. Adapt or replace it with
  a tested graph-aware oracle. Never assume root or state IDs are unchanged.
- `scripts/benchmark_opening_service.py` uses prefix `parent_id`/`child_id`
  fields. Use `benchmark_opening_position_graph.py` for graph measurements;
  adapt lifecycle/HTTP/startup tools only where actual incompatibility demands.
- `scripts/validate_crawler_recovery.sql` hard-codes the bootstrap qualification
  window. Use run-aware monthly integrity/cohort checks rather than applying
  those historical dates to this snapshot; preserve historical drill evidence.
- The frontend proxy's source default is 45,000 ms and max duration is 60 s;
  the release runbook still says 30 s. Reconcile documentation with actual code
  and scoped configuration without automatically raising limits.
- The exact artifact name and Large Functions flag must reach both build and
  runtime scopes for any later protected Preview/Production clone. Sensitive
  credentials must come from existing bound secrets; pulled placeholders are
  not credentials. No environment mutation is authorized by this local slice.

Verify current hosting limits, CLI, scope, protection, alias and rollback target
when preparing the eventual external approval packet. A dated preflight is not
current authorization or proof of hosting eligibility.

## Completion record

The new session must leave a dated implementation/result record with source and
checkpoint identities, exact delta and complete affected-game counts, exclusions,
generation/resume proof, A/B/incremental component parity, raw/component and
transport sizes/hashes, phase timings, peak RAM/disk, backend/frontend/browser
verification, offline transport reconstruction, exact rollback and remaining
external approval actions. Link it from the map and update operational commands
to match tested behavior. Preserve all historical results.

No implementation, full build, transport write, upload or deployment is performed
by creating this handoff. Continue the actual work in the new session using the
prompt below, rather than treating this document as completion evidence.
