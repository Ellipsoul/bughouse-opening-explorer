# Monthly crawler and Player Insights refresh

This is the canonical procedure for the first day of each UTC month. It
refreshes the permanently tracked Chess.com cohort, discovers newly qualifying
players through the observed Bughouse network, creates a checked immutable raw
snapshot, rebuilds every registered Player Insight in one source pass, and
stages or locally publishes the complete browser projection set.

The workflow deliberately does **not** commit, push, upload, promote, or deploy.
The checked JSON projections are the local publication boundary; any Preview or
Production action remains a separate approval-gated release.

## One-command normal run

From `bughouse-opening-explorer` on the first day of the month:

```bash
.venv/bin/python scripts/run_monthly_refresh.py \
  --frontend-data-dir ../bughouse/bughouse-chess/app/data \
  --publish
```

The default period is the previous UTC month. A run started on 1 October, for
example, refreshes September plus mutable October. Its immutable output label
is the current UTC date (`YYYYMMDD`). Supply `--year`, `--month`, or
`--run-label` only for a deliberate historical/retry run.

The command executes these gates in order:

1. Run the durable monthly crawler.
2. Require zero queued, leased, deferred, or failed jobs; zero active runs; and
   no permanently tracked player without a completed or terminal archive
   outcome.
3. Create a SQLite online backup under `snapshots/monthly-<label>/`.
4. Open the backup read-only and immutable, run `PRAGMA quick_check`, require
   zero foreign-key violations, and record its SHA-256 and corpus counts.
5. Build a new shared schema-versioned `player-insights.db` under
   `artifacts/insights/monthly-<label>/`. Existing outputs are never
   overwritten.
6. Export every registered browser projection twice and require byte-identical
   SHA-256 values.
7. Validate the complete staged set before atomically replacing any checked
   file in `bughouse-chess/app/data` when `--publish` is explicit.
8. Emit machine-readable snapshot and insight result records. No deployment is
   performed.

Omit `--publish` to build and validate without changing the checked frontend
files. The staged projections remain in the artifact's `projections/`
directory for review.

## Discovery policy

The monthly crawl is not just a fixed-cohort fetch. It refreshes the completed
month and current partial month for every player with
`tracking_started_at IS NOT NULL`, including currently dormant players. Public
archive records are authoritative corrections and new observations.

Every newly observed opponent is evaluated using timestamped public or
callback-PGN post-game ratings. A player with a rating of at least 2000 on a
Bughouse board inside the run's inclusive rolling one-year window becomes
eligible and permanently tracked. The crawler then queues that player's full
available Bughouse history back to January 2016. After lifetime completion it
adds the bounded deterministic partner-board probes and recursively evaluates
newly observed players. Later dormancy changes current classification only; it
does not end monthly collection.

This strategy discovers the transitive qualifying population reachable from
the existing cohort. Chess.com exposes no global Bughouse feed, so disconnected
populations are outside the crawler's evidence and must not be claimed as
covered.

## Monitoring and interruption

In a second terminal:

```bash
.venv/bin/bughouse-explorer crawl --crawler-db data/crawler.db status --watch
```

Do not estimate completion from queue length alone. Month jobs can qualify new
players, which fan out into archive-list, lifetime-month, and sampled partner
jobs. Completion means the persisted closure audit is ready, not merely that a
visible queue once reached zero.

`Ctrl-C` and `SIGTERM` stop at a durable job boundary. Resume with the exact run
id reported by status so the original eligibility window remains stable:

```bash
.venv/bin/bughouse-explorer crawl --crawler-db data/crawler.db resume RUN_ID
```

After the resumed crawler reaches closure, finalize without starting a second
monthly run:

```bash
.venv/bin/python scripts/run_monthly_refresh.py \
  --skip-crawl \
  --frontend-data-dir ../bughouse/bughouse-chess/app/data \
  --publish
```

If the worker stops because of repeated network/API errors, inspect the HTTP
counters and latest persisted error before resuming. Do not reinterpret an
environmental DNS failure as a Chess.com API failure, and do not weaken the
failure circuit breaker merely to force closure.

## Bounded smoke test

Use a bounded live run only when crawler behavior itself changed:

```bash
.venv/bin/python scripts/run_monthly_refresh.py --max-jobs 5
```

This is expected to stop before snapshotting because closure is incomplete.
Resume the run id with the normal crawler command, then use the `--skip-crawl`
finalization command. Analyzer/export smoke tests should instead use the tiny
repository fixtures; they consume no Chess.com capacity.

## Immutable outputs and retry rules

Default paths for a 1 September 2026 run are:

```text
snapshots/monthly-20260901/crawler-through-2026-08.db
snapshots/monthly-20260901/snapshot-result.json
artifacts/insights/monthly-20260901/player-insights.db
artifacts/insights/monthly-20260901/monthly-refresh-result.json
artifacts/insights/monthly-20260901/monthly-workflow-result.json
artifacts/insights/monthly-20260901/projections/*.json
```

Never delete or overwrite a previous checked snapshot or insight artifact to
make a retry fit. Use a new label such as `20260901-r2`:

```bash
.venv/bin/python scripts/run_monthly_refresh.py \
  --skip-crawl \
  --run-label 20260901-r2 \
  --frontend-data-dir ../bughouse/bughouse-chess/app/data \
  --publish
```

If snapshot creation failed, no final snapshot path is published. If an
analytics build fails, retain its partial directory for diagnosis and choose a
new label after fixing the reduced fixture/test. Never run the multi-minute
analyzer against `data/crawler.db`.

## Verification after the command

Review the result JSON first. It must reconcile snapshot identity, source and
derived checksums, policy/analyzer/schema versions, tracked-player count,
accepted/analyzed/excluded games, bounded anomaly reasons, artifact integrity,
and all projection checksums.

Backend verification:

```bash
PYTHONPATH=. .venv/bin/pytest -q
git diff --check
```

Frontend verification from `bughouse-chess`:

```bash
npm run test:unit
npm run test:component
npm run lint
npm run build
git diff --check
```

Also check `/player-insights` at the narrowest supported phone viewport and a
wide desktop viewport. Exercise every insight, empty search, a newly enrolled
player, zero-game/null behavior, long usernames, minimum-games boundaries,
sort reversal, pagination, and game links. Confirm that the browser receives no
SQLite, raw TCN, internal UUID, content hash, or anomaly evidence.

Record a dated result document containing the before/after crawler counts,
newly enrolled players, run id and request/error counters, snapshot/artifact
identity, analyzer reconciliation, projection raw and deterministic gzip sizes,
test/build/browser evidence, and rollback path.

## Adding a new Player Insight to future monthly runs

Do not add an insight by editing only this runner. First follow
`PLAYER_INSIGHTS_SESSION_PROMPT.md` and
`PLAYER_INSIGHTS_DEVELOPMENT_GUIDE.md`:

1. Write the semantic contract: question, stable id, grain, cohort, eligible
   games, denominator, attribution, malformed-data policy, source/replay needs,
   privacy boundary, UI shape, and exact fixture examples.
2. Add one failing behavioral fixture, the smallest analyzer/schema change to
   pass it, then repeat vertically. Increment every output-changing semantic
   version.
3. Share the source pass only when cohort, eligibility, replay, atomicity, and
   denominator semantics genuinely match the existing build.
4. Add and test a deterministic browser-safe exporter. Keep source evidence and
   operational metadata out of the projection.
5. Register its exporter and filename in
   `PLAYER_INSIGHT_PROJECTIONS` in
   `bughouse_explorer/monthly_refresh.py`. The monthly runner will then stage,
   repeat, checksum, and publish it with the existing set.
6. Add the feature-owned frontend model/component and responsive tests. Static
   delivery remains the default only while the projection is public, bounded,
   and acceptably small.
7. Run a representative benchmark before the first full extraction, then use a
   new immutable run label for the full build.

An insight with a different cohort, security boundary, update cadence,
eligibility policy, or atomic failure policy should use its own analyzer pass or
artifact even if it appears on the same page.

## Rollback and release boundary

The local checked JSON set is the website build input. Before any separately
authorized deployment, retain the previous Git revision or exact projection
files. Rollback means restoring the previous complete projection set and
rebuilding/redeploying the frontend; the immutable raw snapshot and derived
SQLite artifact can remain for reproduction and comparison.

This workflow does not rebuild or release the multi-gigabyte packed Opening
Explorer artifact. When that is desired for the same source snapshot, follow
`MONTHLY_FULL_ARTIFACT_VERCEL_RELEASE_RUNBOOK.md` as a separate approval-gated
operation.
