# Durable incremental opening generations

The full August-to-September migration is proved by complete A/B/incremental
byte parity. See the [dated result](OPENING_INCREMENTAL_RESULT_2026-10-03.md).
The existing independent A/B full-build release gate remains mandatory.
Representative parity alone does not authorize release or replace that gate.

## Routine monthly path

Read this runbook and the latest result for the current parent and source identity.
The original migration analysis, session prompt and live progress log are history;
there is no need to repeat bootstrap when a verified completed parent exists.

1. Validate the new complete immutable snapshot against its completed crawl run.
2. Verify the completed parent, reserve a fresh child/output label and disk budget.
3. Run `update`, or `resume` on the same child/source after an interruption.
4. Export v1, repack v2, audit the delta and compare with the independent A/B gate.
5. Run service/frontend checks and prepare transport for the exact allowed A name.
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

## Complete delta and byte-parity audit

```bash
PYTHONPATH=. .venv/bin/python scripts/report_opening_incremental_delta.py \
  <completed-child-generation> <fresh-delta-report-directory>

PYTHONPATH=. .venv/bin/python scripts/verify_opening_artifact_parity.py \
  <full-v1-a> <full-v1-b> <incremental-v1> --report <fresh-v1-parity.json>

PYTHONPATH=. .venv/bin/python scripts/verify_opening_artifact_parity.py \
  <full-v2-a> <full-v2-b> <incremental-v2> --report <fresh-v2-parity.json>
```

The delta report enumerates every changed UUID, threshold placement and repaired
threshold owner in JSONL, and replays owners to measure complete frontier changes
and newly reached true endings. It records raw/metadata field changes, renames and
every replay exclusion. Its verification time is separate from update/export time.
The parity command recomputes artifact validation and compares component sizes,
SHA-256 and exact manifest serialization. A mismatch leaves its report and fails.

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

For this first migration retain two independent full target builds A/B, two v2
repacks, and the separate incremental comparison export. A alone is a release
candidate. Require exact component size/hash and manifest parity, complete source
metadata parity, representative filtered/unfiltered semantics, source exclusions
and delta reconciliation, complete affected-owner evidence, recovery tests,
resource measurements and local service/browser validation.

Use the graph benchmark and graph-aware HTTP oracle. Preserve 500-node/256-KiB
response defaults and 4,000-node/512-KiB hard caps. The frontend source-default
proxy timeout is 45 seconds and the maximum is 60 seconds; inspect the actual
scoped override before release, without treating Sensitive placeholders as values.

Follow [the full release runbook](MONTHLY_FULL_ARTIFACT_VERCEL_RELEASE_RUNBOOK.md)
for exact A-name transport/stage/runtime allowlists, deterministic offline chunks,
retry/reconstruction, runtime attestation, and the concrete approval packet.
External upload, hosting changes, paid resources, Preview creation, Production
promotion, alias changes, deletion, commits and pushes require separate authority.

When reserving a later month's A name, retain this month's exact name as a
rollback entry in the transport, stage and runtime authorization sets before
changing the candidate constant. Test that both the new A and retained rollback
are allowed, while the new B/comparison names are rejected. Do not replace exact
names with a prefix or wildcard.

Future months use the checked target as parent and the next complete snapshot as
input. Routine dual-full replay may only be replaced by an explicit revised gate
supported by the completed full-scale parity, correction and recovery evidence;
this runbook does not waive it. Rollback keeps the prior artifact/deployment and
restores only the separately approved serving pointer/alias. Dataset-versioned
browser caches then invalidate normally; checkpoints never serve browser reads.

## Current parent and resource planning

The next update's parent is
`artifacts/opening-incremental-20261003-r1/september`, checked with:

```bash
PYTHONPATH=. .venv/bin/python scripts/opening_incremental.py verify \
  artifacts/opening-incremental-20261003-r1/september
```

Its checkpoint is 70,723,231,744 bytes, including an 8,028,999,680-byte complete
support table. Budget the retained parent, independent child copy, full-reference
scratch, exports and transport together. Recheck available space each month.
The dated result contains complete timings/RSS/disk measurements; none is a
promise of next-month duration. Source hashes, semantic policy and engine files
are pinned: avoid cosmetic reformatting of pinned modules during a generation.

Local Vercel package verification must count every destination in
`.vercel/output/functions/api/index.func/.vc-config.json` `filePathMap` plus
wrappers/config. Directory size alone undercounts CLI 62's reference-based
package. Hash mapped artifact files and exclude transport/database/dotenv entries.
Use dummy credentials and process-only flags for local builds. Exact stage,
package measurements and release commands belong in each dated release packet.
