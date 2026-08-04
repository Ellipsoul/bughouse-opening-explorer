# Vercel Large Function preview prompt

Continue work in both repositories:

- `/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer`
- `/Users/aronteh/Desktop/Coding_Adventures/bughouse/bughouse-chess`

Read, in order:

1. `bughouse-opening-explorer/docs/README.md`
2. `bughouse-opening-explorer/docs/VERCEL_LARGE_FUNCTION_PREVIEW_PLAN_2026-08-04.md`
3. `bughouse-opening-explorer/docs/FULL_OPENING_TREE_SCALE_UP_RESULT_2026-08-04.md`
4. `bughouse-opening-explorer/docs/FULL_OPENING_TREE_SCALE_UP_PLAN_2026-08-03.md`
5. `bughouse-opening-explorer/docs/HOSTED_OPENING_EXPLORER_PLAN_2026-08-03.md`
6. `bughouse-opening-explorer/docs/HOSTING_PROVIDER_COMPARISON_2026-08-03.md`
7. `bughouse-opening-explorer/docs/PLATFORM_ARCHITECTURE.md`
8. `bughouse-opening-explorer/docs/PLATFORM_ROADMAP.md`
9. `bughouse-opening-explorer/docs/BACKUP_RECOVERY.md`
10. every applicable `AGENTS.md` file in both repositories before editing in
    its scope.

Treat `VERCEL_LARGE_FUNCTION_PREVIEW_PLAN_2026-08-04.md` as the operative
specification. Treat the completed scale-up result as the measurement and
artifact-identity record; do not rerun the full build merely to start this
slice.

## Goal

Develop and prove an interruption-safe, checksum-verified transport and remote
materialization path for the 2,524,966,683-byte full accepted-game artifact,
then—only after presenting current limits, exact costs and mutations and
receiving explicit approval—deploy artifact A to a protected Vercel Large
Function Preview. Validate it against the representative oracle under the same
query and response budgets. Do not change Production or promote the full
artifact in this slice without a separate explicit approval.

## Current checkpoint

- The full tree contains 6,516,478 accepted games and has dataset version
  `1e876810b96364e4bf9f23d49fb509a843783253`.
- Artifact A is the only upload candidate. Artifact B is an immutable
  correctness/reproducibility oracle.
- The restored source snapshot SHA-256 is
  `04b5694a288f1b0a966524090e991d70aa695096531933710a0a17f25bb5a5ac`.
- The largest component, `games.bin`, is 1,892,357,989 bytes; `nodes.bin` is
  418,508,028 bytes.
- Full local readiness is about 5.96 seconds and peak RSS is about 522 MB.
- The full local service/browser/lifecycle matrix passed without relaxing the
  500-node/256-KiB defaults or 4,000-node/512-KiB hard caps.
- The representative artifact remains live and is the immediate rollback.
- The player-filter fix is merged and deployed.
- No full artifact, paid Blob store, Large Functions configuration mutation,
  or full Production deployment has been authorized or created.

## Authorization boundary

This prompt authorizes read-only inspection, local implementation, tests,
deterministic local chunking/reconstruction rehearsals, documentation, and
cost/limit research. It does **not** by itself authorize:

- uploading any full-artifact byte to Vercel or another provider;
- creating or changing Vercel environment variables or project settings;
- provisioning Blob, a paid plan, storage, a container, or any paid resource;
- changing the frontend service origin, custom domain, or Production alias;
- promoting a deployment; or
- deleting a retained deployment, artifact, snapshot, or credential.

Before the first external upload—even a disposable interruption rehearsal—show
the exact target, byte count, files, expected duration, cost, cleanup, and
rollback, then obtain explicit approval. Approval for a rehearsal does not
authorize the full upload; approval for the full Preview does not authorize
Production promotion.

Never open, serve, modify, or depend on `data/crawler.db`. Do not make Chess.com
requests or resume crawler work. Never send the artifact, SQLite, raw payloads,
postings corpus, or full username corpus to the browser. Never expose a secret
through `NEXT_PUBLIC_*`.

## Workstream 1 — reconcile and preflight

Confirm both repositories are on the intended merged commits and preserve any
unrelated changes. Read-only inspect the current Vercel team, plan, service and
frontend projects, Fluid Compute/Large Functions eligibility, representative
deployment, protection, region, environment scoping, and Production origin.

Refresh current official Vercel documentation for Function package size, CLI
source-file size, build duration and temporary disk, memory, concurrency,
regions, transfer, Blob multipart behavior, storage/operations, pricing,
rollback, and removal. Distinguish documented guarantees from inference. If
remote build headroom or resumption semantics remain undocumented, obtain a
support answer or stop at that gate rather than assuming.

Revalidate artifact A's complete structure and component SHA-256 values and
confirm artifact B remains component-identical. Do not alter either artifact.
Preflight local free disk, memory, file descriptors, temporary write
amplification, recovery headroom, and upload input integrity.

## Workstream 2 — TDD transport boundary

Implement the plan's deterministic 64-MiB chunk manifest, allowlist, journal,
retry, reconstruction, and fail-closed validation using TDD. Keep transport
chunks and journals outside version control.

Tests must cover deterministic ordering; exact and short final parts; missing,
duplicate, reordered, truncated, oversized, and corrupt chunks; wrong sizes and
hashes; journal restart; idempotent retry; allowlist rejection; and byte-exact
representative reconstruction. Run an offline dry run that reports every
included path, source/chunk/reconstructed byte count, digest, temporary-space
requirement, and exclusion.

Do not use `--archive=tgz` for the artifact. Do not assume the ordinary Vercel
deployment uploader resumes within a large file.

## Workstream 3 — interruption proof and approval gates

Present the disposable protected-Preview rehearsal plan and obtain explicit
approval before uploading it. Interrupt an in-progress chunk, restart from the
journal, and demonstrate that acknowledged chunks are reused while only the
incomplete chunk is retried. Reconstruct and verify the original SHA-256, then
demonstrate bounded removal and credential cleanup.

If chunk reuse is not demonstrated, do not upload the full artifact. Present
Vercel Blob multipart as a fallback with current storage, transfer, operation,
build-materialization, cleanup, and plan costs. Do not provision it without
approval.

After a successful rehearsal, present a second preflight for the full upload:
exact immutable target, total and per-component bytes, expected chunk count,
build disk/headroom, Function package size, likely duration, pricing exposure,
protection, validation, rollback, and removal. Obtain explicit approval before
transferring artifact A.

## Workstream 4 — protected full Preview

After approval, upload exactly artifact A and the existing Python service
boundary to the separate opening-service Preview environment. Record local and
remote digests, journal acknowledgements, retries/reused bytes, CLI/API version,
team/project/environment/region, build phases, deployment ID and URL, Function
package size, protection, resource use, and cost.

Reconstruct components during the build, verify exact byte counts and SHA-256,
run complete artifact validation, and exclude transport chunks from the final
Function. A mismatch must fail the candidate without changing the retained
representative or frontend Production origin.

## Workstream 5 — full hosted validation

Run the same local representative/full corpus and budgets against the protected
Preview. Compare cold and warm startup, metadata, root/deep navigation, direct
links, White/Black filters, invalid and stale filters, autocomplete, support
one, endings, drops, terminal/source-game behavior, 1/8/32/64 concurrency,
ETags, cancellation, overload, timeouts, node/byte limits, correction,
rollback, and removal.

Run relevant Python, frontend, integration, browser, TypeScript, ESLint,
production-build, artifact-validation, benchmark, and `git diff --check`
checks. Preserve the existing `/` route and two-board viewer.

Report hosted cold/warm P50/P95/P99, RSS/memory, CPU, errors, transfer,
invocations, provisioned memory, observed cost, and any public-beta behavior.
Compare it directly with the representative and full local evidence.

## End state

Leave Production on the representative artifact. Retain the representative
deployment as immediate rollback. Present the evidence, costs, limitations,
and a recommendation before requesting any Production decision.

Do not commit generated chunks, journals, artifacts, credentials, bypass URLs,
or raw corpora. Preserve unrelated changes. Do not commit or push repository
changes unless explicitly authorized in the new session.
