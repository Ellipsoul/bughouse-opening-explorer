# Hosted opening explorer provider comparison — 3 August 2026

## Decision status

The measured representative winner is a Python Vercel Function with the
validated packed artifact in its immutable deployment bundle, fronted by the
existing same-origin Next.js proxy. The live compatibility probe passed before
the reader was deployed: Vercel extracted and checksum-validated all artifact
components, allowed mmap/random reads from the read-only bundle, reused the same
reader and mapping on a warm instance, completed 64 concurrent random reads
without failure, and stayed below 46 MB peak RSS.

This is a decision for the 91,911-game experiment, not a commitment to the
projected full artifact. The projected 2.58 GB packed file exceeds the standard
500 MB Python bundle path. Vercel's 5 GB Large Functions beta is directionally
relevant, but it is not authorization to build the full artifact and is not yet
a production-scale engineering assumption.

The control is the same reader in a small external container. Vercel Blob,
Neon, and Turso remain measured alternatives rather than fallbacks chosen merely
because the representative sample fits a free allowance. Edge Config is suitable
only for tiny version/flag metadata; Upstash Redis is suitable only for bounded
response caching or rate limiting.

The service and an exact-host Production experiment were deployed only after
explicit approval. No Git commit or push, full build, Blob/database/container
resource, or Production promotion was made.

## Inputs and scale

The only deployable input for this experiment is
`artifacts/opening/representative-mod71-v2-a`:

- 91,911 accepted games;
- dataset/build `e1400ceb14e26dc3cd09e93ac1a4630e88c2ac03`;
- `packed-prefix-interval-v2`;
- 36,782,672 component bytes (35.08 MiB), with every manifest checksum verified;
- projected packed full scale: about 2.58 GB, projection only; and
- representative relational projection: 70.44 MiB, with a projected 5.38 GiB
  full SQLite artifact. PostgreSQL/libSQL physical size must be measured rather
  than assumed equal to SQLite.

The packed reader remains the semantics and performance oracle. No full artifact
was built or uploaded.

## Current official limits

All limits below were checked on 3 August 2026. Provider allowances and prices
can change; re-check the linked primary source immediately before provisioning.

| Candidate | Current official constraints relevant here | Representative fit | Projected full-scale fit and dated cost estimate |
| --- | --- | --- | --- |
| Vercel Python Function, bundled artifact | Standard Python bundle limit is 500 MB uncompressed; filesystem is read-only except `/tmp`, which is writable up to 500 MB; request and response bodies are capped at 4.5 MB; Hobby Fluid compute has 2 GB memory/1 vCPU and up to 300 s duration. Warm instances may reuse memory and `/tmp`, but reuse is not guaranteed. [Function limits](https://vercel.com/docs/functions/limitations), [Python runtime](https://vercel.com/docs/functions/runtimes/python), [runtime filesystem/reuse](https://vercel.com/docs/functions/runtimes) | Yes by size. Local validation+mmap startup was 110.9 ms, incremental peak RSS 9.5 MiB in the reader benchmark; live cold/warm values remain unmeasured. Low preview traffic can fit Hobby's included 1 million invocations, 4 CPU-hours, and 360 GB-hours if observed usage confirms it. [Usage and pricing](https://vercel.com/docs/functions/usage-and-pricing) | The 2.58 GB projection exceeds the standard Python bundle path. Vercel announced a public-beta Large Functions path up to 5 GB on 29 June 2026, but it is not a production assumption and requires a separate full-scale probe. [Large Functions announcement](https://vercel.com/changelog/vercel-functions-can-now-be-up-to-5-gb-in-package-size-7yAwSyCig0IQDXUIDistvS/eadf06d6c3) |
| Vercel Blob + Function materialization | Hobby includes 1 GB-month storage, 10 GB Blob data transfer, 10,000 simple operations, and 2,000 advanced operations. Blob on-demand rates shown are $0.023/GB-month storage, $0.05/GB transfer, $0.40/million simple ops, and $5/million advanced ops. Function `/tmp` remains 500 MB. [Blob pricing](https://vercel.com/docs/vercel-blob/usage-and-pricing) | Artifact storage fits the Hobby allowance. A cold materialization transfers 36.8 MB before validation; 10 GB covers only about 271 complete cold downloads, excluding other traffic. Warm reuse is opportunistic. | The 2.58 GB projection cannot be materialized wholly into Function `/tmp`. Storage alone is about $0.06/month at the posted on-demand rate before allowances, but this architecture fails the disk gate and adds cold transfer/validation. |
| Marketplace Neon Postgres projection | Free currently lists 0.5 GB storage per project and 100 CU-hours/month/project, with up to 2 CU/8 GB. Launch lists $0.106/CU-hour and $0.35/GB-month, with a typical spend starting around $15/month. [Neon pricing](https://neon.com/pricing) | The 70.44 MiB relational sample fits, but requires a new projection and query benchmark against the packed oracle. Cold/warm latency and row/index amplification are unmeasured. | The 5.38 GiB SQLite projection does not fit 0.5 GB. At the listed Launch storage rate, 5.78 decimal GB is about $2.02/month for storage plus compute; Neon advertises a typical Launch spend around $15/month. |
| Marketplace Turso/libSQL projection | Free currently lists 5 GB total storage, 500 million row reads/month, 10 million writes/month, 3 GB sync/month, and one-day PITR. Developer is $5.99/month with 9 GB included and 2.5 billion row reads. Reads are billed by rows scanned, not merely rows returned. [Turso pricing](https://turso.tech/pricing?frequency=monthly), [usage accounting](https://docs.turso.tech/help/usage-and-billing) | The relational sample fits. A projection, indexes, row-scan counts, cold/warm latency, export, and correction benchmark are still required. | The 5.38 GiB projection is above the free 5 GB allowance but below Developer's 9 GB; the posted base price is $5.99/month before overages. |
| Edge Config, metadata only | Hobby currently allows one store, 8 KB total store size, 100,000 reads/month, and 100 writes/month; propagation is documented as up to 10 seconds and backups are retained for seven days. [Edge Config limits](https://vercel.com/docs/edge-config/edge-config-limits) | Appropriate for a dataset-version pointer or preview metadata only. Environment variables are simpler for the first protected preview. | Never an artifact or response store. On-demand reads are listed at $3/million and writes at $1/100 after included usage. |
| Upstash Redis, cache/rate limit only | Free currently lists 256 MB, 500,000 commands/month, and 10 GB bandwidth. Pay-as-you-go lists $0.20/100,000 commands, storage after the first GB at $0.25/GB, and bandwidth above 200 GB at $0.03/GB. [Upstash Redis pricing](https://upstash.com/pricing/redis) | Plenty for a deliberately bounded response cache or token-bucket state, but it duplicates HTTP caching if introduced before evidence. | Not an artifact store or correctness source. Cost depends on hit traffic; no instance should be provisioned until a measured need exists. |
| External container control | Render free web services currently provide 512 MB RAM/0.1 CPU, spin down after 15 idle minutes, can take about one minute to restart, and have an ephemeral filesystem. Starter is 512 MB/0.5 CPU at $7/month. [Free services](https://render.com/docs/free), [compute plans](https://render.com/docs/compute-plans) | Fits the packed artifact and existing mmap reader. Free cold start is deliberately poor but useful as a control; Starter can be continuously available. | The projected artifact needs a persistent image/volume or startup download and more disk planning. It adds a second provider and operational surface. Fly.io is another control, but has no free tier; a shared 1x 512 MB machine is region-dependent and roughly $3–5/month before storage/egress. [Fly pricing](https://fly.io/docs/about/pricing/), [no free tier](https://fly.io/docs/about/cost-management/) |

Vercel's general Hobby allowances include 100 GB Fast Data Transfer and 10 GB
Fast Origin Transfer; these are account-level usage categories, not a promise
that arbitrary origin/blob traffic is free. [Vercel limits](https://vercel.com/docs/limits)

## Option assessment

### 1. Bundled Vercel Function — measured representative winner

It preserves the immutable, versioned packed oracle, avoids a database
translation, avoids per-cold-start Blob download, fits the standard Python
bundle cap, and can memory-map the read-only deployed files. The bounded service
response cap is 512 KiB, comfortably below Vercel's 4.5 MB response limit. The
same-origin proxy retains credentials server-side and keeps browser responses
bounded.

The standalone compatibility probe supplied the missing live evidence before
the service entrypoint was deployed. Checksum plus reader initialization took
617.87 ms on the observed cold instance; the warm call reused the same instance,
reader, and mapping. Sixty-four concurrent random reads had zero failures.
`/var/task` was readable and read-only, the 1 MiB `/tmp` round trip passed, and
the runtime reported about 538 MB free scratch space and Python 3.12.13.

### 2. Blob materialization — viable sample experiment, poor full-scale shape

The sample fits both Blob and `/tmp`, and checksum-before-read is straightforward.
It pays a cold download and must tolerate missing warm reuse. The projected full
artifact is larger than Function `/tmp`, so this does not provide a credible
scale path without range reads, a different reader, or external compute. Those
are architectural changes, not benefits for this slice.

### 3–4. Neon and Turso — projection research, not the first preview

Both can hold the sample, but neither preserves the exact packed access path.
They need schema, index, query-plan, row-scan, correction, export, and semantic
parity benchmarks. Turso is the cheaper posted full projection; Neon provides a
conventional serverless PostgreSQL path. Free-tier sample fit is not sufficient
evidence to select either.

### 5–6. Edge Config and Upstash — narrow support roles

The first preview does not require either. Edge Config could later hold a tiny
active-version record if environment-scoped configuration proves awkward.
Upstash could later enforce shared rate limits or cache hot bounded responses if
the Function's native concurrency and HTTP caching are insufficient.

### 7. External container — comparison control

It is the lowest-rewrite control for the existing mmap service, but adds another
provider, deployment surface, and cross-provider network hop. Render Free gives
an intentionally visible cold-start comparison; Starter supplies an always-on
$7/month baseline. This control should be benchmarked only after approval for an
external deployment.

## Local compatibility and reader results

Commands run without external deployment:

```bash
shasum -a 256 artifacts/opening/representative-mod71-v2-a/{edges.bin,endings.bin,games.bin,nodes.bin,posting-ordinals.bin,postings.bin,strings.bin}
.venv/bin/python scripts/probe_vercel_function_runtime.py artifacts/opening/representative-mod71-v2-a --concurrent-reads 32 --scratch-directory /tmp
.venv/bin/python scripts/benchmark_opening_service.py artifacts/opening/representative-mod71-v2-a --repeats 100 --result docs/OPENING_SERVICE_LOCAL_BENCHMARK_2026-08-03.json
```

Observed on the local Python 3.13.7 process:

- checksum validation succeeded for all seven components;
- probe initialization: 102.45 ms;
- 32 concurrent random mmap reads: zero failures;
- probe peak RSS: 36.89 MiB; one invocation's post-init probe work: 1.28 ms;
- 1 MiB `/tmp` write/fsync/read/checksum round trip succeeded;
- reader validation+mmap startup in the fresh 100-run benchmark: 110.85 ms;
- incremental reader peak RSS: 9.5 MiB;
- P99: exact pair 3.25 ms, unfiltered 5.50 ms, White 7.75 ms, Black 7.88 ms;
- deterministic responses: all four tested filter shapes; and
- adaptive popular-line browser policy: two foreground responses, zero idle
  responses, 337,843 uncompressed bytes / about 38.1 KB zlib-compressed.

Local bundle writability was `true`, as expected on a workstation; Vercel is
documented read-only and must produce `false`. The local probe cannot measure
Vercel cold start, regional latency, autoscaling, or reuse. `vercel build` was
also stopped before pulling project settings: an unlinked standalone build
requires Vercel project settings, and creating/linking a service project is part
of the approval-gated external step.

The sanitized benchmark evidence is
[`OPENING_SERVICE_LOCAL_BENCHMARK_2026-08-03.json`](OPENING_SERVICE_LOCAL_BENCHMARK_2026-08-03.json).

## Protected preview and Production experiment contract

`bughouse-chess` has separately named Preview and Production decisions. Hosted
flags are server-only:

- `OPENING_EXPLORER_PREVIEW_ENABLED=true`;
- `OPENING_EXPLORER_PREVIEW_HOSTS=<exact preview hostname list>`;
- `VERCEL_ENV=preview` on the server;
- `OPENING_EXPLORER_PRODUCTION_ENABLED=true` only for the separately approved
  trial;
- `OPENING_EXPLORER_PRODUCTION_HOSTS=<exact Production hostname list>`;
- `OPENING_EXPLORER_SERVICE_URL=<bare HTTPS origin>`;
- `OPENING_EXPLORER_SERVICE_ALLOWED_ORIGINS=<exact origin list>`;
- `OPENING_EXPLORER_SERVICE_TOKEN=<server-only bearer token>`; and
- optional `OPENING_EXPLORER_SERVICE_TIMEOUT_MS`, bounded to 100–10,000 ms.

The page and sidebar share the same pure decision. The page and proxy also
enforce it server-side. The old local flag cannot enable a production-mode
build. Production requires its own explicit flag, `VERCEL_ENV=production`, and
an exact configured host; Preview uses different names and cannot enable
Production. The service URL, token, and hosted flags are never `NEXT_PUBLIC_*`.
Vercel Authentication Standard Protection protects raw deployment URLs on
Hobby; the generated deployment hostname returned the Vercel login boundary,
while only the approved aliases served the experiment. [Deployment Protection](https://vercel.com/docs/deployment-protection),
[environment variables](https://vercel.com/docs/environment-variables)

The read boundary validates the manifest/checksums before app creation, exposes
unauthenticated `/healthz` and authenticated `/readyz`, reports dataset/format/
adapter/terminal versions, enforces the existing request/response hard caps,
uses a bounded semaphore with a short queue timeout, emits strong deterministic
ETags, suppresses request logging, and returns immutable private caching headers
for versioned reads. The same-origin proxy forwards only an explicit read-path
allowlist, `If-None-Match`, ETag, cache, and timing headers.

## Deployment, validation, correction, rollback, and removal

The following workflow was exercised through correction. Rollback and removal
remain deliberately non-destructive procedures while the approved trial is
live.

1. Create or link the separate `bughouse-opening-explorer-service` project.
   Store the bearer token as a sensitive, server-only Vercel variable.
2. Stage only the probe source, Python package files needed by it, and the exact
   representative artifact; confirm the staged file list contains no `data/`,
   SQLite, raw payload, alternate artifact, or username export. The checked-in
   `.vercelignore` is an allowlist beginning with `/*`, following Vercel's
   documented allowlist form. [Vercel deployment exclusions](https://vercel.com/docs/deployments/vercel-ignore)
3. Run `vercel build --target preview --local-config vercel.probe.json`, inspect
   `.vercel/output/functions` size and file list, then deploy the prebuilt probe.
4. Call the protected probe cold, warm, after inactivity, and concurrently.
   Record P50/P95/P99, instance IDs, RSS, scratch capacity, bundle writability,
   checksum result, response bytes, region, concurrency errors, and cost usage.
5. Only if every gate passes, add the read-service entrypoint and deploy the same
   immutable artifact version. Validate `/healthz`, authenticated `/readyz`,
   stale version 409, invalid/budget errors, 304 validators, 512 KiB cap,
   concurrency 503, and no sensitive logs.
6. Configure `bughouse-chess` with the service origin, origin allowlist, timeout,
   and sensitive token in the intended Vercel scope. Configure a separately
   named exact-host flag for Preview or, as explicitly approved here,
   Production. Build and deploy without promotion.
7. For correction, publish a separately versioned validated artifact; never
   overwrite the active version. Change only the Preview version/origin after
   readiness succeeds. Roll back by restoring the previous Preview pointer and
   redeploying Preview.
8. Remove by first disabling the applicable named flag and redeploying. Validate
   page and proxy not-found behavior, then delete the experiment deployment and
   service deployment/project and remove scoped credentials. Recheck `/` and
   the two-board viewer. Vercel project/deployment deletion is irreversible and
   must not be run while the trial is wanted.

At that initial hosted checkpoint, no `promote` or `bughouse-chess` push
occurred. The service correction was
demonstrated by deploying `dpl_RBEbqdXbzbdvZb35y9e1ErEtKb1p` over the first
experiment `dpl_9yQ6AmpKWQHx5LksXaEwE84mr6ZN`. Final E2E verification exposed
and isolated a sidebar hydration regression, and the green build was deployed
as `dpl_BznoEMsf1DsuJ3XoYpoGpDwEpmCG`. The corrected experiment
`dpl_RBEbqdXbzbdvZb35y9e1ErEtKb1p` is the immediate rollback; the previous
known-good normal site `dpl_HMv41ofK4dyrtLzdf7jy9EKfMGdV` is the removal
rollback.

On 3 August 2026, after the hosted experiment was explicitly approved for
early-user testing, a UI-only production-target build was first uploaded without
the custom domain as `dpl_ASFjX9SUHXwxBrxjKpjqj2Yuq2PV`. The exact-host gate
correctly returned not-found on its temporary Vercel hostname. After live root,
support-one source-game, and internal-ending checks, a final singular-copy fix
was built and promoted as `dpl_9Qi28BuG74BjUjYuw2CQ3gMsuU7c`. No repository
push or service/artifact upload occurred during that refinement. The preceding
UI build `dpl_ASFjX9SUHXwxBrxjKpjqj2Yuq2PV` is its immediate rollback, and
`dpl_BznoEMsf1DsuJ3XoYpoGpDwEpmCG` remains the earlier hosted rollback.

## Hosted result and remaining full-scale blocker

Authenticated health/readiness, metadata, root, stale-version, hidden-artifact,
ETag, and eight-way concurrency checks passed. The eight concurrent roots were
all HTTP 200, with end-to-end P50 688.866 ms and P95/P99 3,112.858 ms. The real
browser passed the popular mainline, branch/backtrack, direct deep link, White
filter, filter-change backtrack, support-one leaf, internal ending, retained
drop checkmate, lazy game details, and browser back/forward checks. A test-first
correction fixed a missing filtered overlay when returning to a structurally
cached ancestor.

The browser-cache comparison selected immutable HTTP caching: a repeated deep
node used zero transfer and 0.3 ms versus 308.8 ms cold. Cache Storage and
IndexedDB worked but added writes, lifecycle, quota, and corruption handling
without a material benefit. See
[`HOSTED_OPENING_SERVICE_BENCHMARK_2026-08-03.json`](HOSTED_OPENING_SERVICE_BENCHMARK_2026-08-03.json)
and [`BROWSER_CACHE_COMPARISON_2026-08-03.md`](BROWSER_CACHE_COMPARISON_2026-08-03.md).

At representative traffic the observed deployment fits Vercel Hobby's included
allowances, so the estimated incremental monthly platform cost is $0 while the
account remains within those dated limits. The projected full artifact is not
costed as a standard Function because it does not fit that supported bundle
path. Large Functions beta, an external container, or a projection must be
measured only in a separately authorized full-scale slice.
