# Durable incremental opening generations

The full August-to-September migration is proved by complete A/B/incremental
byte parity. See the [dated result](OPENING_INCREMENTAL_RESULT_2026-10-03.md).
Effective 2 November 2026, explicit user authorization supersedes the former
mandatory full A/B and full-versus-incremental byte-parity gate for routine
updates. The routine gate is `incremental-integrity-v1`, specified below.
Independent full comparisons are reserved for explicitly requested audits or
relevant algorithm/policy migrations; small regression fixtures may still use
full replay as an oracle.

## Routine monthly path

Read this runbook and the latest result for the current parent and source identity.
The original migration analysis, session prompt and live progress log are history;
there is no need to repeat bootstrap when a verified completed parent exists.

1. Validate the new complete immutable snapshot against its completed crawl run.
2. Verify the completed parent, reserve a fresh child/output label and disk budget.
3. Run `update`, or `resume` on the same child/source after an interruption.
4. Export v1, repack v2, audit and reconcile the complete delta, and execute the routine acceptance gate.
5. Run regression/recovery, local service and desktop/mobile frontend checks. The validated incremental v2 export is the routine candidate; use its exact allowed name.
6. Follow the [release runbook](MONTHLY_FULL_ARTIFACT_VERCEL_RELEASE_RUNBOOK.md)
   for separately authorized Preview, Production and rollback actions.

Bootstrap/validated-seed commands below are recovery and initial-migration tools.
Use them only when there is no compatible completed parent.

## Inputs and generations

Use complete checked snapshots, never the live crawler or diagnostic subsets.
The period is a corpus label, not an end-time filter. Retain historical backfills
and partial current-month games. Record SHA-256, read-only SQLite integrity,
latest completed run, qualification window and cohort closure before building:

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_opening_snapshot.py \
  <snapshot.db> --run-id <latest-completed-run-id> --sha256 <sha256>
```

Reserve a fresh output label and capacity for parent plus child checkpoints,
discovery spills, full-reference scratch, exports, transport and rollback. Never
remove retained input or scratch to force a run to fit. Inspect owned processes
before invoking a writer; each generation also holds a nonblocking writer lock.

The ledger retains every UUID, source order, complete adapter fields, admission
and replay outcome, prior changed revision, and metadata independent of raw game
hashes. Deleted UUIDs remain tombstones with their stable keys. Complete placement
counts and owner accumulators cover hidden tails. Materialized facts remain
separate from support contributions, so frontier repair cannot count a game twice.
Only a finished checksummed generation may be a parent or export source.

## Bootstrap

```bash
PYTHONPATH=. .venv/bin/python scripts/opening_incremental.py bootstrap \
  artifacts/opening-incremental-<label>/august \
  --snapshot <checked-august.db> --snapshot-sha256 <sha256>
```

A plain bootstrap performs admission/replay, durable external placement sorting,
materialization, full support/owner consistency checks, and completion hashing.
This is the one-time corpus-sized migration cost. Discovery spills have registered
checksums and cursors; unregistered spills left after an interruption are retained
and excluded from resume. No replay-cache or serving-format change is introduced.

To reuse retained materialized facts, first prove their exact correspondence with
an immutable v1 artifact. The validator exports every staging component to a new
directory, compares the full manifest, hashes the staging file, and writes its
certificate only on success:

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_opening_staging_seed.py \
  <retained-staging.sqlite3> <validated-august-v1-artifact> \
  artifacts/opening-incremental-<label>/seed-validation
```

Then add `--validated-seed <seed-validation>/validated-seed.json` to bootstrap
(or to an interrupted bootstrap still in the ingest phase). Input source/policy
must match. Every accepted game's metadata must match the reference. Missing
reference games are replayed and must be actual exclusions. Complete hidden-tail
support is still rediscovered; old shared-key files are insufficient. Seed facts
are copied into the new checkpoint and remapped to stable internal game keys.
The original staging is opened immutable and is never changed.

## Monthly update

```bash
PYTHONPATH=. .venv/bin/python scripts/opening_incremental.py update \
  artifacts/opening-incremental-<label>/september \
  --parent artifacts/opening-incremental-<label>/august \
  --snapshot <checked-target.db> --snapshot-sha256 <sha256>
```

The child begins as an independent SQLite backup of its checked parent. It scans
all normalized target rows to identify additions, removals, corrections, renames
and source-order changes. It replays changed move/admission revisions for signed
distinct-placement contributions, then repairs the complete owner set affected by
final-batch promotion/demotion. Metadata-only corrections update outcomes and
player postings without topology replay. Parent bytes remain valid throughout.

## Interruption, retry, and invalidation

```bash
PYTHONPATH=. .venv/bin/python scripts/opening_incremental.py resume \
  <same-generation-directory> --snapshot <same-snapshot.db> \
  --snapshot-sha256 <same-sha256>

PYTHONPATH=. .venv/bin/python scripts/opening_incremental.py verify \
  <completed-generation-directory>
```

Keep the original process log. Confirm the owned writer has stopped before resume.
SQLite uses WAL and FULL synchronous transactions. Admission, support and repair
cursors commit with their facts; external discovery chunks are synced before
registration. Seed import commits table-by-table. Completion is manifest-last,
with a checksum of the checkpoint and pinned semantic/engine versions. Repeating
a completed run verifies it and changes no data. If seed indexing was interrupted,
repeat the same `--validated-seed` argument until ingestion has completed.

A reader that blocks the final WAL checkpoint prevents publication of completion.
Release that reader and resume the same generation. Verification rejects a nonempty
WAL or a completion manifest whose source/stage/policy differs from the immutable
main database. Never copy only the main SQLite file from an unfinished writer.

A source checksum, checkpoint checksum, engine/policy mismatch, incomplete parent,
corrupt registered spill, or inconsistent support/owner is a hard failure. Do not
repair it by reading the live crawler, changing expected counts, or silently
accepting another policy. A semantic change requires an explicitly labelled
rebuild/migration and independent full parity. Keep the previous complete parent.

## Canonical export and v2 repack

```bash
PYTHONPATH=. .venv/bin/python scripts/opening_incremental.py export \
  <completed-generation> --output <fresh-incremental-v1-directory>

PYTHONPATH=. .venv/bin/python scripts/repack_opening_position_graph_v2.py \
  <incremental-v1-directory> <fresh-incremental-v2-directory>
```

Export reassigns public game ordinals in target source order, excludes unreferenced
objects, sorts canonical structural identities, and rebuilds dictionaries/offsets
through the same independently tested exporter. Internal keys never become public
IDs. The full builder continues to consume the checked source independently and
never consumes a checkpoint.

An interrupted export leaves its partial output and scratch intact. Retry export
under a fresh output label; never overwrite it or call it valid without its final
manifest and complete artifact validation. Repack has the same fresh-output rule.

## Routine acceptance gate: incremental-integrity-v1

Use the checked complete snapshot and an explicit exclusive UTC cutoff. This
October update uses `end_time < 1793491200`; November games and qualification
based solely on November must not enter its source or insights. The retained raw
acquisition is provenance, not the bounded analysis input.

```bash
PYTHONPATH=. .venv/bin/python scripts/report_opening_incremental_delta.py \
  <completed-child-generation> <fresh-delta-report-directory>
PYTHONPATH=. .venv/bin/python scripts/validate_opening_incremental_release.py \
  --source <checked-target.db> --source-sha256 <sha256> --cutoff <exclusive-epoch> \
  --parent <completed-parent> --child <completed-child> \
  --artifact <incremental-v2-directory> --delta <delta-report-directory> \
  --report <fresh-acceptance.json>
PYTHONPATH=. .venv/bin/pytest -q
```

For a fresh post-export evidence directory, `scripts/run_opening_incremental_checks.py`
orchestrates repack/delta (reusing completed outputs), acceptance, v1/v2 semantic
checks, backend regression and graph checks. Pass `--source`, `--source-sha256`,
`--cutoff`, `--parent`, `--child`, `--v1`, `--v2`, `--delta`, and `--evidence`.
It acquires the generation writer lock, refuses overwrites, never launches a full
builder, and explicitly leaves HTTP/browser/frontend evidence pending. Do not
run it alongside an existing supervisor or export writer; adopt or finish that
writer first. Interrupted exports/repack need fresh output paths.

The gate rejects source checksum/cutoff/integrity/closure violations, mismatched
parent linkage or source/policy identities, incomplete or uncheckpointed children,
and changed checkpoint bytes. Completion must include the engine's full support
and owner consistency stage: positive support, accepted singleton owners, shared
counts and XOR membership accumulators, replay of touched singleton owners,
root reconciliation, membership ownership and exactly two player postings per
accepted game. Reuse that completed proof only with unchanged checkpoint hashes
and pinned implementation policy; do not repeat the expensive stage needlessly.

The complete delta report replays affected threshold owners and enumerates all
source changes, corrections, metadata/renames, removals, admission changes,
exclusions, promotion/demotion placements and repaired owners. The acceptance
checker independently compares parent/child ledgers and reconciles every ordered
change witness, totals, exclusions, threshold placement and owner witness. It
also checks full source UUID/order/date coverage and validates all exported
component bytes/hashes/structure, source fingerprint and accepted-game totals.

Require the backend regression suite, including incremental correction/deletion,
threshold and durable recovery fixtures, acceptance rejection fixtures, and exact
transport/stage/runtime allowlist tests. Retain passed frontend unit/component,
type/lint/build checks when inputs have not changed. Compare v1-to-v2 semantic
metadata and sampled states (a format conversion check, not an independent full
rebuild), then run local graph/startup/HTTP-oracle checks and desktop/mobile
browser checks. Record each result separately; the acceptance JSON alone is not
proof that browser or regression checks ran.

The routine release candidate is the **validated incremental v2 export**. Retain
its v1 export, parent/child completion records, cutoff lineage, delta JSONL,
acceptance report, test and browser evidence, and previous rollback artifacts.
No routine phase may launch or wait for full A/B builds or treat their intentional
cancellation as failure. When replacing a live supervisor, disable its launch and
wait paths first, adopt the existing incremental process, then stop only owned
full-reference/dependent jobs and record intentional cancellation. Retain partials.

Assurance limit: this proves pinned-source consistency, durable incremental
invariants, complete delta accounting, artifact integrity and tested behavior.
It does **not** prove byte identity to an independently rebuilt corpus; common-mode
adapter, incremental-engine or exporter defects remain possible. An explicit
full-rebuild audit or relevant policy/algorithm migration can add that stronger
comparison; it is not a routine prerequisite. Do not claim cancelled checks passed.

The local filesystem receiver rehearsal is:

```bash
PYTHONPATH=. .venv/bin/python scripts/rehearse_opening_transport_locally.py \
  <exact-allowed-A-artifact> /private/tmp/<fresh-external-release-directory>
```

It double-generates the deterministic manifest, writes chunks, retains a partial
receipt, resumes through the existing journal after interruption and a transient
failure, proves a completed retry transfers nothing, reconstructs and validates
the received bytes, and creates/verifies the minimal source stage. It never calls
a remote uploader. Retain its local-only journal separately from future remote
acknowledgements; it is not evidence that a hosting provider has received bytes.

## Required release evidence

For routine months retain the acceptance evidence above and exact incremental
candidate identity. For an explicitly requested full audit or relevant migration,
add independently built full references and complete component/manifest comparison
as specified by that audit; historical migration evidence remains preserved.

Use the graph benchmark and graph-aware HTTP oracle. Preserve 500-node/256-KiB
response defaults and 4,000-node/512-KiB hard caps. The frontend source-default
proxy timeout is 45 seconds and the maximum is 60 seconds; inspect the actual
scoped override before release, without treating Sensitive placeholders as values.

Follow [the full release runbook](MONTHLY_FULL_ARTIFACT_VERCEL_RELEASE_RUNBOOK.md)
for exact incremental-candidate transport/stage/runtime allowlists, deterministic offline chunks,
retry/reconstruction, runtime attestation, and the concrete approval packet.
External upload, hosting changes, paid resources, Preview creation, Production
promotion, alias changes, deletion, commits and pushes require separate authority.

When reserving a later month's incremental candidate name, retain this month's exact name as a
rollback entry in the transport, stage and runtime authorization sets before
changing the candidate constant. Test that both the new candidate and retained rollback
are allowed, while unapproved full/comparison names are rejected. Do not replace exact
names with a prefix or wildcard.

Future months use the checked target as parent and the next complete snapshot as
input. Full rebuild comparisons require an explicit audit or relevant migration.
Rollback keeps the prior artifact/deployment and restores only the separately
approved serving pointer/alias. Dataset-versioned browser caches then invalidate
normally; checkpoints never serve browser reads.

## Current parent and resource planning

The next update's parent is
`artifacts/opening-incremental-20261101-october-only-r3/october`, checked with:

```bash
PYTHONPATH=. .venv/bin/python scripts/opening_incremental.py verify \
  artifacts/opening-incremental-20261101-october-only-r3/october
```

Its checkpoint is 71,690,526,720 bytes, SHA-256
`a5b7c35015fca00c210271cd7be747fd32e5cd74e20f78a90a9d8714fe11e469`.
It is built from the October-only source recorded in
`OPENING_INCREMENTAL_RESULT_2026-11-02.md`. Budget the retained parent,
independent child copy, discovery/repair spill, exports and transport together. Recheck available space each month.
The dated result contains complete timings/RSS/disk measurements; none is a
promise of next-month duration. Source hashes, semantic policy and engine files
are pinned: avoid cosmetic reformatting of pinned modules during a generation.

Local Vercel package verification must count every destination in
`.vercel/output/functions/api/index.func/.vc-config.json` `filePathMap` plus
wrappers/config. Directory size alone undercounts CLI 62's reference-based
package. Hash mapped artifact files and exclude transport/database/dotenv entries.
Use dummy credentials and process-only flags for local builds. Exact stage,
package measurements and release commands belong in each dated release packet.
