# Monthly full-artifact Vercel release runbook

## Purpose

Use this runbook when publishing the next immutable monthly opening snapshot.
It captures the sequence that successfully moved the 2.525-GB August 2026
artifact through an interruption-safe upload, remote reconstruction, protected
Preview, exact oracle, and Production cutover.

This is an operational checklist, not standing authorization. Obtain explicit
approval before every external artifact upload, Vercel environment or project
mutation, paid resource, Production deployment, alias change, or deletion.

> **Position-graph gate (September 2026).** The compact
> `packed-position-graph-v2` artifact has been reconstructed and validated
> locally at 3,386,496,490 component bytes. Its format and measurements are in
> [`PACKED_POSITION_GRAPH_V2_RESULT_2026-09-03.md`](PACKED_POSITION_GRAPH_V2_RESULT_2026-09-03.md).
> No upload or deployment was performed or authorized by that reconstruction.
> Refresh current Vercel limits and obtain the separate approvals below before
> beginning any external release work.

Never use `data/crawler.db` at any step. Build only from a separately restored,
checksummed, SQLite-validated snapshot. Never send an artifact, SQLite file,
raw payload, postings corpus, or full username corpus to the browser. Never put
a credential in `NEXT_PUBLIC_*`.

## Stable identifiers

| Item | Value |
| --- | --- |
| Vercel team | `team_kjpopfvj3bLNk74leLtqEgAD` / `aronteh-projects` |
| service project | `prj_BUO6dAAVzaQAhjbFlJ7e5Lt1I2dP` / `bughouse-opening-explorer-service` |
| frontend project | `prj_UZ9keRku6D5IQXQk48VQZtX8htBl` / `bughouse-chess` |
| service canonical alias | `bughouse-opening-explorer-service.vercel.app` |
| public frontend | `bughouse.aronteh.com` |
| service region | `iad1` |
| chunk size | 67,108,864 bytes (64 MiB) |

Record these again at the start of each release; do not assume project, team,
plan, protection, region, alias, or environment state is unchanged.

## Release ledger

Create a dated result document and fill this ledger before any upload:

| Field | Required value |
| --- | --- |
| restored snapshot path | immutable path outside `data/crawler.db` |
| restored snapshot SHA-256 | exact lowercase digest |
| artifact A path | only upload candidate |
| artifact B path | immutable reproducibility oracle |
| dataset version | manifest-derived digest |
| accepted games | exact count |
| component bytes | exact sum, excluding artifact manifest |
| component manifest | path, bytes, SHA-256 for every component |
| A/B comparison | component-identical, or stop |
| local startup and RSS | cold/warm latency and peak RSS |
| retained rollback ID | currently active known-good deployment |
| Vercel CLI versions | local and remote builder |
| plan and limits | current official documentation and live plan |
| approvals | rehearsal, full Preview, Production, cleanup separately |

## Phase 1 — reconcile before building

1. Read `docs/README.md`, this runbook, the latest dated Production result,
   `VERCEL_LARGE_FUNCTION_PREVIEW_PLAN_2026-08-04.md`, and every applicable
   `AGENTS.md` in both repositories.
2. Confirm both repositories' branches, commits, remotes, and dirty files.
   Preserve unrelated changes. Do not commit or deploy them.
3. Read-only inspect the Vercel team, plan, project IDs, Fluid Compute and Large
   Functions eligibility, region, deployment protection, Production aliases,
   frontend service origin, current Production metadata, and rollback ID.
4. Refresh official Vercel limits and pricing. Separate documented guarantees
   from observed behavior and inference.
5. Verify local disk, memory, file descriptors, and temporary write headroom.
   Budget for the restored snapshot, A, B, deterministic chunks, staged source,
   reconstructed artifact, and one recovery copy at the same time.
6. Verify the latest Vercel CLI locally. Run an exact local Large Functions
   build before uploading. A stale CLI can incorrectly enforce the ordinary
   500-MB Python boundary even when the remote 5-GB beta path is enabled.

Stop if the current Large Functions limit, remote build disk, plan eligibility,
or source-retention behavior is unknown and material to the release.

## Phase 2 — restore and build two immutable artifacts

Follow `BACKUP_RECOVERY.md` to restore a separate monthly source snapshot.
Record the compressed and restored hashes and rerun the SQLite integrity and
domain-invariant checks against that restored copy. Do not substitute the live
crawler database.

Use month-specific immutable names. First build the semantic v1 oracle from the
checked snapshot, then deterministically repack it as the browser-serving v2
artifact. Replace every angle-bracket value and use separate output and
temporary directories for A and B:

```text
.venv/bin/python scripts/build_opening_position_graph.py \
  <restored-snapshot.db> \
  artifacts/opening/<monthly-v1-oracle-name>-a \
  --temporary-directory <absolute-temp-a> \
  --snapshot-sha256 <restored-snapshot-sha256> \
  --sample-modulus 1 \
  --sample-remainder 0 \
  --result <absolute-v1-build-a-result.json>

.venv/bin/python scripts/repack_opening_position_graph_v2.py \
  artifacts/opening/<monthly-v1-oracle-name>-a \
  artifacts/opening/<monthly-v2-artifact-name>-a
```

Repeat both commands for artifact B with different output and temporary
directories. Preserve the v1 builds as local semantic oracles; only v2 A is an
upload candidate. Then:

1. run complete artifact validation on A and B;
2. record every component byte count and SHA-256;
3. run `diff -rq <v2-artifact-a> <v2-artifact-b>`;
4. confirm accepted-game, node, edge, ending, skip, and dataset-version counts;
5. mark A as the only upload candidate and make B immutable;
6. preserve the restored snapshot SHA-256 as the source identity.

If A and B are not component-identical, stop. Do not select the artifact that
merely looks more plausible.

## Phase 3 — update the explicit monthly allowlist using TDD

The service intentionally rejects unapproved artifact directory names. Before
staging a new month:

1. add a failing test for the exact new artifact-A name;
2. update the explicit allowlists in
   `bughouse_explorer/opening/vercel_stage.py` and
   `bughouse_explorer/opening/vercel_hosted.py`;
3. keep artifact B rejected;
4. keep representative and obsolete names read-only or rejected according to
   the current rollback policy;
5. run the focused tests, then the complete Python suite.

Do not generalize the allowlist to a directory glob or arbitrary environment
value. Exact names are a publication safety boundary.

## Phase 4 — repeat the local performance and lifecycle matrix

Run, at minimum:

```text
.venv/bin/python scripts/benchmark_opening_startup.py <artifact-a> --repeats 20
.venv/bin/python scripts/benchmark_opening_service.py <artifact-a> --repeats 20
.venv/bin/python scripts/benchmark_opening_publication_lifecycle.py <current-artifact> <artifact-a> <absolute-temp-current-pointer.json>
```

Start the local read service only against artifact A and run the HTTP,
concurrency, cancellation, ETag, filter, ending, drop, source-game, hard-cap,
and browser matrix from the latest result. Keep the default 500-node/256-KiB
budgets and 4,000-node/512-KiB hard caps unless a separate design change is
approved.

Compare the new cold-start distribution with the frontend's current 30-second
upstream timeout and 60-second Function duration. If representative cold or
filtered requests approach 30 seconds, stop and make an explicit hosting/UX
decision before Production. Do not silently raise the boundary.

## Phase 5 — prepare deterministic transport offline

Use a new month-specific directory under `/private/tmp`; never put chunks or
journals in either repository.

First run the preparer without `--write` and review its full inclusion and
space report. Then write chunks:

```text
.venv/bin/python scripts/prepare_vercel_transport.py <artifact-a> \
  --chunk-directory <absolute-chunk-directory> \
  --manifest-output <absolute-transport-manifest.json> \
  --chunk-size 67108864

.venv/bin/python scripts/prepare_vercel_transport.py <artifact-a> \
  --chunk-directory <absolute-chunk-directory> \
  --manifest-output <absolute-transport-manifest.json> \
  --chunk-size 67108864 \
  --write
```

Reconstruct offline from those chunks into a fresh destination. Verify every
component size and SHA-256, total source/chunk/reconstructed bytes, deterministic
ordering, exact final short parts, and complete artifact validation. Record all
excluded paths. The transport must contain only the artifact manifest and the
seven packed components.

Stage the exact service boundary plus chunks:

```text
.venv/bin/python scripts/stage_vercel_large_preview.py \
  <absolute-transport-manifest.json> \
  <absolute-chunk-directory> \
  <absolute-stage-directory>
```

Review `bundle-manifest.json`. It must exclude snapshots, SQLite, raw data,
artifact B, other artifacts, credentials, journals, and repository history.

## Phase 6 — prove journal restart before the monthly full upload

Do a small disposable protected-Preview rehearsal first. Present the exact
target, byte count, files, estimated duration, cost model, cleanup, rollback,
and credential handling; obtain explicit rehearsal approval.

Use `--interrupt-path` and `--interrupt-after-bytes` to stop inside one chunk.
The first run must not acknowledge the incomplete file. Restart with the same
stage and journal. Record:

- acknowledged file and byte count before interruption;
- incomplete part path and interruption offset;
- acknowledged files/bytes reused after restart;
- files/bytes retried;
- reconstructed SHA-256 and complete validation;
- disposable deployment ID and its confirmed removal.

If acknowledged content is uploaded again, or the incomplete chunk is treated
as complete, stop before the full upload.

## Phase 7 — handle credentials without redaction placeholders

This is the most important failure lesson from August 2026.

Vercel Sensitive values returned by `vercel env pull` are placeholders such as
`(Sensitive)`, not the original secret. Never source, copy, hash-compare as if
meaningful, or inject such a pulled value into a deployment. Doing so creates a
Function that authenticates the placeholder rather than the real frontend.

The deployment client now fails closed on known `(Sensitive)`, `[SENSITIVE]`,
and `[REDACTED]` values in runtime or build environments. Keep that test.

For a protected Preview, use a separately approved, short-lived Preview bearer
token obtained from a real secret source, never from `vercel env pull`. Keep it
in a mode-0600 temporary file/process environment, do not print it, use it only
server-side, and remove it after the Preview. If no real Preview credential is
available, stop at this gate.

For Production, let Vercel bind the existing Sensitive Production project
variable. Do not manually populate `OPENING_EXPLORER_SERVICE_TOKEN` from a
pulled env file. Before promotion, verify by key and scope—not value—that the
service and frontend both have their server-only Production credential.

## Phase 8 — full upload and protected Preview

Run the uploader without `--execute` first. Preserve its exact preflight. The
real execution requires the manifest ID printed by that dry run:

```text
.venv/bin/python scripts/upload_vercel_large_preview.py \
  <absolute-stage-directory> \
  <absolute-upload-journal> \
  --team-id team_kjpopfvj3bLNk74leLtqEgAD \
  --project-id prj_BUO6dAAVzaQAhjbFlJ7e5Lt1I2dP \
  --project-name bughouse-opening-explorer-service \
  --runtime-env-key OPENING_EXPLORER_SERVICE_TOKEN \
  --build-env-key VERCEL_SUPPORT_LARGE_FUNCTIONS \
  --create-preview
```

After explicit full-Preview approval, repeat with `--execute` and the exact
`--confirm-manifest-id`. Supply `VERCEL_TOKEN`, the real short-lived Preview
service token, and `VERCEL_SUPPORT_LARGE_FUNCTIONS=1` through the current
server-side process only. Do not place them in arguments, reports, Git, or a
browser variable.

On retry or a service-only correction, use
`--reuse-acknowledgements-from-stage` and
`--reuse-acknowledgements-from-journal`. Reuse is permitted only when path,
bytes, SHA-1, and SHA-256 all match. Record reused, uploaded, and retried bytes.

In the remote build log require:

1. exact reconstructed bytes;
2. exact dataset version;
3. complete artifact validation status;
4. adequate free bytes before materialization and required headroom;
5. `enabling large functions (beta)`;
6. transport exclusion from the final Function;
7. expected Python runtime, memory, timeout, and region.

Run the sanitized byte-exact oracle and the 1/8/32/64 concurrency matrix against
the protected Preview. Run the frontend unit, integration, browser, TypeScript,
ESLint, Production-build, artifact-validation, and `git diff --check` gates.

## Phase 9 — Production preflight and promotion

Present a second approval packet containing the immutable deployment target,
total and per-component bytes, journal reuse, Function size, build headroom,
likely duration, current Hobby allowances/rates, beta status, protection,
validation plan, exact rollback alias command, and exact cleanup list.

Before promotion, update the service project's Production-scoped non-secret
values, with approval:

- `VERCEL_SUPPORT_LARGE_FUNCTIONS=1`;
- `OPENING_EXPLORER_ARTIFACT_NAME=<exact-new-artifact-a-name>`.

Keep the existing Sensitive `OPENING_EXPLORER_SERVICE_TOKEN`; do not replace it
with a pulled placeholder.

Treat `vercel promote` as a new Production clone and remote rebuild, not an
atomic alias move. The clone must independently reconstruct, checksum, validate,
and package the full artifact using Production environment scope. Capture the
new deployment ID; it will not be the protected Preview ID.

After explicit Production approval:

```text
vercel promote <validated-preview-deployment-id> --scope aronteh-projects
```

Monitor through `READY`. Warm the generated Production URL using the unsecret
`/healthz` endpoint. Then verify the public frontend metadata identifies the
new dataset, followed by root and exact oracle checks. A direct probe using a
value obtained from `vercel env pull` is not an authentication test.

## Phase 10 — cutover correction and rollback

Classify failures before changing anything:

| Symptom | Likely boundary | Action |
| --- | --- | --- |
| build fails near 500 MB | Large Functions flag missing from the clone's build scope | stop candidate; restore flag before a new clone |
| direct service accepts only `(Sensitive)` | redaction placeholder was injected | remove candidate; redeploy using Vercel-bound real Production secret |
| public proxy returns `401` while service health is 200 | frontend/service credentials do not match | restore rollback alias; inspect environment scope without printing values |
| public proxy returns `503` near 5 seconds | stale explicit proxy timeout | verify Production timeout scope and deployed Function duration |
| cold public request succeeds in 18–30 seconds | expected full-artifact cold tail | record and monitor; do not call it warm latency |
| normal rollback returns Hobby `402` | target is deeper than one Production deployment | use the retained deployment's direct alias rollback |

The reliable bounded rollback is:

```text
vercel alias set <retained-known-good-deployment-id> \
  bughouse-opening-explorer-service.vercel.app \
  --scope aronteh-projects
```

Immediately verify public metadata identifies the retained dataset. Do not
delete that deployment or its local artifact. Restore the new full deployment
with the same alias command only after the failed boundary is corrected and
validated.

## Phase 11 — final Production evidence

Against the public same-origin proxy, repeat the exact local oracle for metadata,
root/deep/direct links, White/Black/exact/invalid/stale filters, autocomplete,
endings, drops, source games, invalid nodes, hard caps, and hosted `304`.
Reports must omit filter values and usernames.

Record:

- cold and warm P50/P95/P99 by query shape;
- 1/8/32/64 status counts and latency tails;
- Function package digest/bytes, memory, duration, runtime, and region;
- errors, timeouts, invocations, transfer, and available usage data;
- current official Hobby allowances and comparison rates;
- observed monetary charge separately from consumed included usage;
- any metrics Vercel does not expose, without inventing values.

Use an automated browser to verify the opening route has meaningful content,
no error overlay/page errors, full root counts, move navigation, filters, and
direct links. Verify `/` and the two-board viewer. Capture unrelated warnings as
such.

## Phase 12 — cleanup, documentation, and publication

After the full Production path passes:

1. retain the active full deployment and one explicitly named known-good
   rollback deployment;
2. remove only recorded failed, placeholder-token, rehearsal, and superseded
   Preview deployments authorized for cleanup;
3. remove short-lived Preview credentials and exact temporary env/token copies;
4. keep chunks, journals, and sanitized reports outside Git only as long as the
   retention policy requires;
5. confirm Git contains no artifact, chunk, journal, credential, bypass URL,
   snapshot, raw corpus, or generated filter value;
6. write a dated result with artifact identity, deployment IDs, mutations,
   failures/corrections, validation, cost, cleanup, and rollback;
7. run complete tests and `git diff --check` in both repositories;
8. commit and push only with explicit authorization.

## Definition of success

The release is complete only when:

- A and B are component-identical;
- journal interruption/restart is proved;
- remote reconstruction matches every local byte count and SHA-256;
- the protected Preview and public Production proxy match the local oracle;
- public cold and 64-concurrency requests fit the approved timeout;
- the browser shows the full counts and preserves the existing viewer;
- Production points to the new full artifact;
- a named known-good deployment remains a tested alias rollback;
- failed and placeholder-token candidates and temporary credentials are gone;
- exact costs, included-usage exposure, and beta limitations are documented;
- the release result and runbook changes are committed without generated or
  sensitive material.
