# Full opening-tree scale-up prompt

> **4 August 2026 status:** local workstreams are complete. Do not rerun the
> full build or upload the artifact by treating this prompt as unfinished.
> Continue from
> [`FULL_OPENING_TREE_SCALE_UP_RESULT_2026-08-04.md`](FULL_OPENING_TREE_SCALE_UP_RESULT_2026-08-04.md).
> The next action is an explicit approval decision for a protected, preview-only
> Vercel Large Functions trial; Production remains separately gated.

Continue work in both repositories:

- `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer`
- `/Users/aronteh/Desktop/Coding_Adventures/bughouse/bughouse-chess`

Read, in order:

1. `bughouse-opening-explorer/docs/README.md`
2. `bughouse-opening-explorer/docs/HANDOFF_2026-08-01.md`
3. `bughouse-opening-explorer/docs/FULL_OPENING_TREE_SCALE_UP_PLAN_2026-08-03.md`
4. `bughouse-opening-explorer/docs/OPENING_EXPLORER_VERTICAL_PROTOTYPE_2026-08-03.md`
5. `bughouse-opening-explorer/docs/HOSTED_OPENING_EXPLORER_PLAN_2026-08-03.md`
6. `bughouse-opening-explorer/docs/HOSTING_PROVIDER_COMPARISON_2026-08-03.md`
7. `bughouse-opening-explorer/docs/PLATFORM_ARCHITECTURE.md`
8. `bughouse-opening-explorer/docs/PLATFORM_ROADMAP.md`
9. `bughouse-opening-explorer/docs/BACKUP_RECOVERY.md`
10. every applicable `AGENTS.md` file in both repositories before editing in
    its scope.

## Goal

Measure and explain the opening explorer's first-load latency, then scale the
settled packed-prefix-interval-v2 tree to the full accepted-game corpus locally.
Use that measured full artifact to make a current hosting decision and, only
after presenting the deployment plan/costs and receiving explicit approval,
stage and publish it to the live production boundary with reproducible rollback
and removal.

Do not assume the initial delay comes from data size. The current client makes
two sequential bounded requests: metadata, then one root or deep-link
neighborhood capped at 500 nodes/256 KiB by default. Instrument browser,
proxy, process import, manifest/checksum validation, mmap/reader construction,
query, serialization, transfer, cache merge, replay, and first useful paint
separately. Determine which phases are constant, file-count-dependent,
artifact-byte-linear, postings-dependent, or bounded by request limits.

## Current checkpoint

- The validated representative artifact contains 91,911 games, is about
  36.8 MB, and remains the correctness/performance oracle.
- The production representative is a checksum-validated bundled Python Vercel
  Function behind the server-only same-origin Next.js proxy.
- The client never downloads the artifact, retains a 5,000-node memory LRU,
  and uses immutable HTTP caching.
- Route, sidebar, and proxy are always available in local, Preview, and
  Production builds. Availability flags have been removed.
- Local development requires the Python reader on `127.0.0.1:8765` plus the
  Next.js app on port 3000.
- Query defaults remain depth five, 500 nodes, and 256 KiB; hard caps remain
  4,000 nodes and 512 KiB.
- The prior full artifact estimate is approximately 2.58 GB, but the next slice
  must measure the final artifact rather than treating that projection as fact.

## Authorization and safety boundaries

- Never open, serve, modify, or operationally depend on `data/crawler.db`.
- Do not make Chess.com requests or resume crawler work.
- A full derived build is authorized only from an explicit, separate,
  restored, SQLite-validated snapshot with a recorded SHA-256. If no such input
  is available, stop and present the blocker.
- Preflight free disk, temporary write amplification, memory, source checksum,
  SQLite integrity, and rollback headroom before beginning the full build.
- Never overwrite or delete the validated representative artifact. Build the
  full tree into a new immutable version directory.
- Do not send the packed artifact, SQLite, raw payloads, postings corpus, or
  full username corpus to the browser.
- Preserve exact decoded move-prefix node identity and all settled terminal,
  posting, filtering, result, and game-reference semantics.
- Preserve the existing `/` route and two-board viewer behavior.
- Preserve the existing service-origin allowlist, server-only credential,
  HTTPS, timeout, concurrency, query, and response-budget protections.
- Do not upload the full artifact, mutate Vercel configuration, provision a
  paid resource, create an external production deployment, or promote anything
  until local evidence, current official limits, costs, rollback, and deletion
  procedures have been presented and explicit approval is obtained.
- Do not expose credentials through `NEXT_PUBLIC_*` variables.
- Preserve AGPL attribution and corresponding-source obligations.
- Preserve unrelated changes. Do not commit or push unless explicitly
  authorized in the new session.

## Workstream 1 — first-load phase analysis

Add low-cardinality instrumentation and reproducible commands that separate:

- browser route/hydration and first useful paint;
- metadata and root-neighborhood request waterfalls;
- Next.js proxy and network time;
- cold import/application construction;
- manifest parsing and per-file checksum validation;
- file opens, mmap creation, mapped versus resident bytes, and page faults;
- bounded reader traversal, filtering, encoding, compression, and transfer;
- client cache merge, board replay, and render; and
- cold process, warm process, HTTP-cache hit, and browser-memory hit.

Run repeated representative baselines and report P50/P95/P99, CPU, RSS,
mapped/resident bytes, page faults, bytes read/transferred, and errors. Establish
whether checksum validation or any other readiness phase is linear in artifact
bytes before the full build.

## Workstream 2 — full local artifact

Use TDD for behavior changes. Verify the explicit snapshot and available space,
then run the existing deterministic streaming writer into a new full-version
directory. Record accepted count, input checksum, source fingerprint, phase
times, progress, temporary/final bytes, peak RSS, CPU, write amplification,
component checksums, deterministic rebuild evidence, and semantic validation.

Start the existing reader against the full artifact and run the same
representative benchmark corpus without relaxing budgets. Compare cold/warm
startup, metadata, root/deep neighborhoods, navigation, filters, support-one,
endings, drops, direct links, concurrency, stale versions, correction,
rollback, and removal. Investigate regressions before changing architecture.

## Workstream 3 — full-scale hosting decision

Use current official provider documentation and live read-only Vercel project
inspection. Re-evaluate Vercel Large Functions beta/current successor first,
then object-storage materialization, a small external container control, and
database projection only if warranted. Record dated limits and links for bundle
size, memory, duration, disk, cold start, concurrency, regions, egress, cost,
export, correction, rollback, deletion, lock-in, and AGPL source delivery.

The packed reader remains the correctness/performance oracle. Do not select a
database merely because a free tier fits a sample.

## Workstream 4 — staged production validation

After presenting the local evidence and obtaining explicit deployment
approval, stage a new immutable service version without replacing the
representative. Pass readiness/checksum, smoke, concurrency, semantic, browser,
stale/cancellation, cost, correction, rollback, and removal checks. Compare
production cold/warm behavior with local measurements. Obtain a separate
approval before switching the production service version, and retain the
representative deployment as immediate rollback.

## Required durable outputs

- First-load phase diagram, instrumentation, commands, and representative/full
  measurements.
- Full-build manifest, checksums, timing/resource report, reproducibility
  evidence, and semantic validation—or an evidence-backed blocker.
- Local representative-versus-full service/browser benchmark.
- Dated current hosting comparison and measured decision.
- Staged deployment, validation, correction, rollback, removal, cost, and AGPL
  procedures.
- Updated README, handoff, architecture, roadmap, backup/recovery, hosted plan,
  and this scale-up plan.

## Definition of done

The slice is complete when the first-load delay is explained by measurements;
the full tree is reproducibly built and validated locally or has a concrete
blocker; bounded local navigation/filter/terminal behavior passes at full
scale; a current hosting decision is made; any production change was separately
approved and demonstrated over HTTPS with rollback/removal; and no live raw
database, crawler request, browser artifact transfer, unbounded corpus,
unauthorized cost, or unrelated viewer regression occurred.

Run relevant Python, frontend, integration, and browser tests; TypeScript,
ESLint, production builds; artifact validation; representative/full benchmark
traces; and `git diff --check` in both repositories.
