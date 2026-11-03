# Monthly update operator checklist

Start here for a routine completed-month refresh. This is the workflow contract;
the linked runbooks describe its implementation. Dated results are evidence, not
scripts to rerun. User instructions override default release/browser steps.

## Freeze the run contract before starting a writer

Record once in a dated operations directory:

- Target completed UTC month and **exclusive end-time cutoff**, the first instant
  of the following UTC month. Preserve earlier history/backfills. Do not infer
  a date filter from an artifact name or `--year/--month`.
- Crawl run ID and acquisition policy; checked analysis snapshot path and SHA-256.
  Raw acquisition may contain newer observations, but a completed-month analysis
  must not. New cohort qualification must also be based on retained evidence.
- Last completed parent checkpoint and checksum; pinned policy/implementation;
  fresh child/export/evidence labels; exact incremental-v2 candidate name.
- Frontend/backend commits, dirty files, rollback projections/deployment, free
  disk, and current owned processes. Preserve existing work and partial outputs.
- Scope: local publication, external upload, target environment, browser checks,
  cleanup. Do not repeatedly ask for an authorization already given. Preview is
  the default release path, but an explicit direct-Production instruction skips
  Preview. Never infer permission to commit, push, delete or buy resources.

## Execute each stage once, with evidence

| Stage | Completion evidence | Recovery |
| --- | --- | --- |
| Acquisition | persisted crawl closure and exact run configuration | resume same run; zero queue alone is insufficient |
| Bounded analysis source | cutoff/cohort lineage, SQLite integrity/FKs, no WAL dependency, immutable read-back and SHA-256 | retain raw source; finish/repair clone under a fresh label |
| All Player Insights | shared-source reconciliation, deterministic projection exports, complete set validation, rollback copies | preserve completed publication; retry only failed stage |
| Incremental child | parent/source identities, durable completion, support/owner proof | inspect processes; resume same child/source, never a duplicate writer |
| Export/acceptance | v1/v2 artifacts, complete delta, `incremental-integrity-v1`, regression/recovery and local service evidence | reuse completed outputs; incomplete export/repack uses fresh paths |
| Frontend | applicable unit/component/E2E, lint/types/build and UI evidence | retain passing unchanged-input evidence; inspect failures before retry |
| Transport/package | exact allowed candidate, deterministic chunks, local recovery rehearsal, file inventory, all mapped Function bytes/hashes | separate local rehearsal and remote acknowledgement journals |
| Authorized release | target/team/project/rollback, live auth/plan, remote reconstruction/attestation, READY aliases, API oracle | resume acknowledged chunks; ambiguous deployment POST requires remote inspection before retry |
| Closeout | dated result, actual limits/failures, current parent/candidate/Production pointers | disable obsolete supervisors and delete only the explicitly temporary follow-up automation |

Routine acceptance removes **independent full A/B replay and full-versus-incremental
byte parity**. It does not remove source integrity, complete delta reconciliation,
artifact checksums/structure, regression/recovery tests or API verification.
Never launch full references unless an audit or relevant migration requests them.
See [incremental runbook](OPENING_INCREMENTAL_RUNBOOK.md).

## Known automation gaps — do not mistake instructions for implemented features

1. `scripts/run_monthly_refresh.py` still snapshots the whole acquired database.
   Its `--snapshot` is an **output path**, not an existing bounded input. Its
   default crawl includes the current partial month. Therefore its one-command
   `--publish` path is **not a completed-month-only pipeline**. Do not run it as
   one until a reusable cutoff/cohort step is implemented and regression-tested.
   The October recovery implementation and invariants are described in the
   [cycle review](MONTHLY_UPDATE_REVIEW_2026-11-03.md); its dated script is not a
   generic next-month command.
2. `scripts/run_opening_incremental_checks.py` is the reusable **post-export**
   orchestrator, not an end-to-end monthly supervisor. It deliberately leaves
   frontend/HTTP/browser evidence pending. No single tracked controller currently
   spans acquisition, cutoff, insights, generation, transport and release.
3. The streaming uploader accepts a process `VERCEL_TOKEN`; it does not refresh
   an expiring CLI session. Refresh/verify authentication immediately before use,
   keep secrets out of arguments/logs, and stop on 401/403 rather than interpreting
   them as a transport corruption. `whoami` may be cached; use an authenticated
   project GET. Retain the same remote journal after credential recovery.
4. The generic hosted oracle targets the protected service. For the public
   frontend proxy, use the same request cases without exporting service secrets;
   compare identical HTTP content encodings before asserting exact ETag equality.
   Preserve original failures and prove conditional GET independently. Do not
   weaken body/status checks to make a report pass.

These gaps are engineering follow-ups, not claims that the next run is already
one-click. Add fixture tests before promoting cycle-specific scripts into tooling.

## Execution rules that prevent unnecessary recovery

- Quiet output is not a hung process. Inspect the exact child process, CPU,
  durable progress and log timestamps. Reconstruction can be silent for minutes.
  Stop a writer only with evidence; inspect surviving children before restarting.
- SQLite context managers commit but do not necessarily close connections. Close
  explicitly, checkpoint, confirm journaling state, reopen immutable, validate,
  hash, and publish the completion marker last. Never hash an incomplete main DB.
- On a host restart, reconcile processes and durable markers first. Do not restart
  completed insights/tests or abandoned full-reference jobs. Superseded waiters
  must be disabled, and follow-up prompts updated when policy changes.
- Browser driver output belongs under ignored `output/playwright/`, also excluded
  by ESLint. Do not commit generated probes or lint them as application source.
- Keep logs for flaky test failures and successful reruns. An observed pass does
  not diagnose or fix flakiness. Distinguish sandbox port restrictions and expected
  error-path stderr from real assertion failures; never bypass pre-push gates.
- Pin the CLI used for the local package check and record the remote builder
  version. Measure `filePathMap` destinations plus wrappers, not directory size.
  Build a fresh copy of the validated stage with dummy credentials; never upload
  that local build copy or its environment fixture.
- Keep one status/result record per stage. Use fresh files for retry evidence.
  Never report cancellation as a passed check, or public UI loading as proof of
  complete source/delta correctness.

## Runbooks

- [Acquisition, cutoff and Insights](MONTHLY_DATA_AND_PLAYER_INSIGHTS_RUNBOOK.md)
- [Incremental generation and acceptance](OPENING_INCREMENTAL_RUNBOOK.md)
- [Transport, hosting and release](MONTHLY_FULL_ARTIFACT_VERCEL_RELEASE_RUNBOOK.md)
- [October cycle review and remaining work](MONTHLY_UPDATE_REVIEW_2026-11-03.md)
