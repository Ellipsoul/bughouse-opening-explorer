# Monthly update review — October corpus, completed November 2026

The data update and Production release succeeded, but the path was more manual
than the phrase “monthly workflow” suggested. The documentation was detailed;
it was not consistently current or sufficiently explicit about which operations
were already automated. Operator mistakes also contributed. Neither a host
restart nor transient test failures were caused by missing documentation.

## What caused friction, and what changed

| Issue this cycle | Cause | Improvement / remaining boundary |
| --- | --- | --- |
| November games entered initial acquisition | documented crawler default refreshes previous and current partial month; a “through October” filename did not filter rows | freeze exclusive cutoff before writers; distinguish acquisition from analysis; flag the existing runner's unbounded behavior prominently |
| Cohort could still depend on November after filtering games | qualification pointers and permanent tracking are separate from game membership | bounded clone must repair retained qualification evidence and exclude new November-only qualification without undoing historical permanent membership |
| r2 clone did not finalize as intended | SQLite connection lifetime/WAL state was not explicit enough | r3 closes/checkpoints, uses standalone journaling, validates immutable read-back, then hashes/publishes; never use a main DB while its WAL is required |
| Expensive independent full A/B builds | former runbooks required them; the user explicitly changed the policy | routine `incremental-integrity-v1`, complete delta and regression/recovery replace full replay comparisons; keep full audit/migration option and explicit assurance limits |
| Host restart stopped workers | external interruption; progress split across several supervisors | resume exact child/source, preserve spills/checkpoints, rebuild only incomplete disposable outputs; do not restart completed insights/tests |
| Old waiters and follow-up prompt still described full builds | policy changed while orchestration was active | disable old launch/wait paths before stopping children; adopt incremental worker; record intentional cancellations and update follow-up instructions |
| Release selection still assumed full A | historical naming and exact allowlists encoded a former workflow | incremental v2 is the candidate; retain exact older rollback names, reject comparison artifacts, no wildcard permissions |
| Pre-push lint caught generated browser probes | Git ignore and ESLint ignore are independent | frontend ESLint now excludes `output/playwright/**`; keep generated evidence out of source scope |
| Test runs appeared broken/flaky | sandbox port binding, expected error-path stderr, and user-observed flakiness are different causes | retain actual logs and exit codes; 573 unit, 161 component and 36 E2E passed in the rerun; no claim that a test defect was diagnosed/fixed |
| CLI calls stalled on authentication | cached identity and interactive behavior obscured absence/expiry of credentials | `CI=1`; real authenticated project GET before upload; refresh access token through CLI; retain journal and stop treating auth failure as chunk corruption |
| Quiet local build was stopped unnecessarily | reconstruction produced no intermediate stdout while still doing useful work | inspect exact child/CPU/durable progress before termination; first partial retained, fresh copy completed; this was an operator error |
| Function size looked implausibly tiny | modern CLI maps files outside the Function directory | count all `filePathMap` destinations plus wrapper/config and hash included artifact files; measured 3,537,974,762 bytes, not the 74-KB wrapper directory |
| Preview preparation became unnecessary | user explicitly chose direct Production | separate transport preparation from release target; inherit Production secret; explicit user scope supersedes default Preview sequence |
| Strict hosted oracle flagged ETags despite identical data | protected-service oracle reused against CDN/frontend proxy; compression introduces weak validators | retain raw failures; compare exact decoded body/status plus same opaque digest and actual 304 behavior for the public proxy; direct service and proxy are different boundaries |
| Current docs still said no Production release | results/map were frozen at local completion | publish a dated Production result and update current pointers; preserve historical results unchanged |

The early acquisition included 3,176 November boards. They remain only in retained
raw provenance; the approved analysis source has 8,835,204 boards and cutoff
`end_time < 1793491200`. It repaired 72 qualification pointers and excluded the
new November-only qualifying player from the analysis cohort. No further crawl
was needed for the correction. Those numbers are evidence for this cycle, not
hard-coded assertions for the next one.

## The streamlined next run

Use [one operator entrypoint](MONTHLY_UPDATE_OPERATOR_CHECKLIST.md), then the
three canonical runbooks for source/insights, incremental tree and release.
Freeze month, cutoff, parent, labels and authorization once. Progress through
stage completion records, not separate ad-hoc terminal narratives. Reuse
completed proofs only when their pinned inputs are unchanged. Archive obsolete
waiters, preserve rollback, and report source/data identities at closeout.

The current reusable post-export checker is `scripts/run_opening_incremental_checks.py`.
It never launches independent full references. Its scope is deliberately narrower
than the entire monthly workflow. The tested deterministic transport and journal
remain useful: this upload sent 84 files / 3,526,568,287 bytes, and Production
reconstruction emitted the same attestation as the checked local package.

The strongest improvement is removing repeated whole-corpus replay from routine
months while retaining the checks that directly protect incremental correctness:
source cutoff/integrity, parent-child linkage, durable completion, full support/
owner consistency, complete additions/corrections/removals/exclusion/threshold
delta reconciliation, exported component integrity and regression/recovery.
This is not “no validation.” Common-mode algorithm/exporter defects remain an
assurance limit without an independent full rebuild.

## Engineering work still needed before calling this seamless

These items were identified, not implemented by the documentation review:

1. **Reusable completed-month source builder and runner integration.** Accept
   an explicit cutoff, prior permanent-cohort baseline and immutable acquired
   source. Parameterize the tested clone/qualification rules; validate rolling
   eligibility semantics, FK/integrity, finalization and immutable read-back.
   Add month/year-boundary, null/future date, qualification-only-later, historical
   cohort and interrupted-finalization fixtures. Do not copy the October script's
   fixed hashes, counts, usernames or paths into next month's command.
2. **One durable monthly controller.** Persist input hashes, stage statuses,
   writer ownership, child process identity, elapsed/progress/last heartbeat,
   output manifests and approval scope. Reconcile after reboot; never redo a
   completed stage or wait on an intentionally cancelled audit. Adopt the
   existing post-export checker rather than creating a second implementation.
3. **Reusable authenticated release driver.** Separate prepare/upload/create/
   verify, make Preview versus Production explicit in flag names and reports,
   refresh credentials safely, stop early on auth errors, and persist an
   idempotent deployment request/result boundary. The current generic uploader
   misleadingly calls Production creation `--create-preview`; its preflight
   text must be fixed and covered by tests before relying on it as a release UI.
4. **Two supported HTTP oracles.** Protected service and public proxy should
   share request witnesses but have explicit authentication/validator contracts.
   Add fixtures for strong/weak tags, digest mismatch, absent/malformed validators,
   compressed decoded equality, and conditional responses. Keep raw evidence.
5. **Test reliability follow-up if reproduced.** A successful rerun is not a
   flake fix. Capture failing assertions/seeds/environment before changing tests.

These are focused implementation tasks, not reasons to repeat the successful
October processing. Until they exist, the checklist deliberately calls out the
manual handoffs rather than promising a one-command monthly update.

## Evidence

- [Source/Insights result](MONTHLY_DATA_AND_PLAYER_INSIGHTS_RESULT_2026-11-01.md)
- [Incremental acceptance and parent](OPENING_INCREMENTAL_RESULT_2026-11-02.md)
- [Transport/package preflight](OPENING_UPLOAD_PREFLIGHT_2026-11-02.md)
- [Production release](OPENING_PRODUCTION_RELEASE_2026-11-03.md)
- Local operations: `artifacts/opening-production-20261103-r1/` and
  `artifacts/opening-upload-20261102-r1/`; retained old/superseded operations
  preserve interruptions and cancelled full-build evidence.

No new corpus processing, product-code changes, commits, pushes or deletions were
performed by this review. Browser verification was left to the user as requested.
