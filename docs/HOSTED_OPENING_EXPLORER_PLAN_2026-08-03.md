# Hosted representative opening explorer plan — 3 August 2026

## Decision and objective

The next slice will put the validated 91,911-game representative opening tree
behind a private or explicitly experimental web deployment. The purpose is to
validate the real network boundary, deployment mechanics, client caching, and
operational cost before choosing infrastructure for the full dataset. It is not
authorization to build the full 6.52-million-game artifact or expose the local
prototype automatically from the production `bughouse-chess` application.

The representative packed v2 artifact is 36,782,672 bytes. That is small enough
to test several free-tier or near-free hosting shapes. Because `bughouse-chess`
already runs on Vercel, investigate Vercel-native compute, storage, preview, and
Marketplace solutions first. Keep the final choice open: do not assume a
managed database is preferable merely because one can hold the sample. The
selected reader is designed around an immutable memory-mapped artifact, and
translating it into rows may increase latency, cost, implementation complexity,
and future migration work.

## Preserved boundaries

- Never upload, serve, copy into a derived store, or operationally depend on
  `data/crawler.db`.
- Publish only a validated immutable representative artifact with its manifest,
  checksum, dataset version, policy versions, and explicit provenance.
- Never send the artifact, SQLite, raw payloads, postings corpus, or full
  username corpus to the browser.
- Keep neighborhood, player-prefix, and game-detail responses bounded and
  versioned. Preserve stale-version rejection and hard node/byte caps.
- Keep the existing production `bughouse-chess` flag disabled until a separate
  preview/staging exposure mechanism is designed, tested, and explicitly
  approved. Do not silently weaken the current `NODE_ENV=production` guard.
- Do not make Chess.com requests, crawl, mutate raw data, or build the full
  artifact in this slice.
- Preserve the existing `/` viewer and the opening explorer's feature boundary.
- Preserve AGPL attribution and corresponding-source obligations for any
  network-accessible modified service.

## Workstream A — current hosting research and decision record

Use current official documentation and pricing pages; free-tier limits and
platform behavior are time-sensitive. Start with the Vercel-native paths below,
then retain at least one non-Vercel/container control so platform convenience
does not predetermine the result. Compare every viable shape using the same
artifact and query corpus:

1. **Vercel Function with packaged artifact.** Determine whether a Node.js or
   Python Vercel Function can include and read or memory-map the immutable sample
   from its deployment bundle while meeting current bundle, memory, duration,
   concurrency, and cold-start limits. Do not port the reader until a minimal
   compatibility probe validates the filesystem and packed-access assumptions.
2. **Vercel Blob plus Function-local materialization.** Store the versioned
   artifact and manifest in Blob, use ETags/checksums, and materialize a verified
   local copy only if the runtime provides sufficient reusable ephemeral disk.
   Measure every cold download, warm reuse, readiness, regional transfer, and
   failure cleanup; never stream the Blob object to the browser as the product
   read path.
3. **Vercel Marketplace database projection.** Compare at least Neon Postgres
   and Turso/libSQL if their current free tiers and limits qualify. Prototype
   only if the provider can preserve exact-prefix semantics, bounded indexed
   queries, postings intersections, immutable dataset versions, and predictable
   export/rollback. Compare bytes, latency, implementation cost, and migration
   path against the packed reader; do not make it the new source of truth.
4. **Vercel support services.** Consider Edge Config only for tiny deployment
   metadata such as the active dataset version or preview flag, and Upstash
   Redis only for bounded response caching or rate limiting. Neither should hold
   the opening tree without evidence that its access and cost model fits.
5. **External/container control.** Start the existing reader against a read-only
   local file baked into a small container, or download it from immutable object
   storage before readiness. This control measures the value or cost of staying
   entirely inside Vercel.

Record rejected platforms and reasons. Evaluate region availability, custom
domains/TLS, sleep and cold-start behavior, memory and disk limits, maximum
response/runtime duration, concurrency, bandwidth/egress, observability,
backup/export, vendor lock-in, and the projected cost of both the representative
and full 2.58-GB artifact. Prefer the simplest shape that preserves the selected
artifact and can later scale or be replaced without changing browser semantics.

## Workstream B — hosted read boundary

Adapt the local service boundary without treating its Python framework or exact
JSON field names as frozen:

- bind safely in the hosted runtime while retaining a loopback-only mode for
  local development;
- validate the manifest and checksum before readiness succeeds;
- expose health/readiness separately from dataset metadata;
- use HTTPS, explicit allowed origins or the same-origin Next.js proxy, strict
  timeouts, response-size enforcement, bounded concurrency, and basic abuse
  protection;
- publish immutable dataset-version cache keys, deterministic ETags or an
  equivalent validator, and compression-friendly responses;
- ensure logs and metrics never contain raw payloads or an exported username
  corpus;
- record cold/warm latency, physical and resident memory, mapped virtual memory,
  startup time, response bytes, errors, restarts, and provider cost; and
- demonstrate deployment, health validation, version correction, rollback, and
  removal of the experiment.

Do not add public authentication prematurely, but do not mistake an unlisted URL
for access control. Use the hosting platform's preview protection or a minimal
documented access boundary if the deployment is not intended for unrestricted
public use.

## Workstream C — Vercel preview and `bughouse-chess` integration

Use a non-production Git branch and Vercel Preview Deployment as the default web
test surface; do not promote it. The current feature gate deliberately makes
the explorer unavailable in every production-mode build, including a normal
Vercel preview build, so design a separately named preview/staging gate rather
than deleting that protection. The deployment should:

- keep the normal production site unchanged unless explicitly approved;
- expose the route and sidebar link together in one named preview environment;
- keep the hosted service origin server-side and allowlisted; never expose
  credentials in `NEXT_PUBLIC_*` variables;
- retain the same-origin bounded proxy unless measurements justify direct
  browser-to-service requests;
- use Vercel environment-variable scoping so preview service origins and any
  credentials are unavailable to Production and never committed;
- validate the preview deployment before considering Vercel `promote`; promotion
  remains explicitly out of scope for this slice;
- show dataset/policy coverage and clear service, stale-version, corruption,
  quota, and unavailable states; and
- run direct-route, sidebar, back/forward, filter, terminal-game, drop, stale
  cancellation, and disabled-production checks against the hosted endpoint.

The opening-explorer repository may be pushed independently, but any future
`bughouse-chess` push or preview deployment requires a new explicit approval.

## Workstream D — persistent browser cache experiment

Keep the 5,000-node in-memory LRU as the fast, bounded working set. Compare
three second-tier strategies before selecting IndexedDB:

1. normal HTTP caching with immutable dataset-version URLs and validators;
2. the browser Cache Storage API for complete bounded responses; and
3. IndexedDB records keyed by dataset version, node id, record kind, and
   normalized filter identity.

IndexedDB can retain substantially more structural data across page reloads and
sessions, but browser quota is variable and storage may be evicted. If it wins,
use asynchronous reads, schema/version migrations, dataset-version garbage
collection, quota/error recovery, bounded recency metadata, and an explicit
policy for whether filter overlays are persisted. Never block first render on a
full persistent-cache scan, and never use IndexedDB to store the packed artifact
or an unbounded username corpus.

Measure cold revisit, warm revisit, navigation latency, network requests and
bytes avoided, main-thread time, persistent bytes, write amplification, quota
failure, dataset publication, and cleanup. The simplest strategy that produces
material measured benefit should win; IndexedDB is a candidate, not a settled
requirement.

## Shared hosted query corpus

Use the same deterministic representative artifact and traces already used
locally, including:

- root and the popular seven-position mainline;
- branch, backtrack, alternate branch, deep sparse path, and direct deep link;
- unfiltered, White, Black, exact-pair, support-one, and filter-change cases;
- actual internal endings, identical lines, the retained short drop checkmate,
  and sole-game leaf details;
- cold start, warm instance, one/several concurrent users, provider restart,
  stale dataset version, correction, and rollback; and
- cold browser, memory-cache hit, persistent-cache hit, quota failure, and
  cache cleanup after a dataset-version change.

Compare local and hosted P50/P95/P99 service and end-to-end latency, response and
compressed bytes, requests per navigation, blocked clicks, cache utilization,
error rate, startup/RSS/disk, and observed or projected cost. Record operational
complexity and failure modes, not only the fastest result.

## Definition of done

The slice is complete when:

1. current official provider evidence and a written decision explain why the
   selected sample-hosting shape beat the alternatives, with Vercel-native
   options evaluated first;
2. one reproducible command or deployment workflow publishes the validated
   representative version and one removes or rolls it back;
3. a protected preview of `/opening-explorer` exercises the hosted service over
   HTTPS without changing the normal production site;
4. the full navigation/filter/terminal/stale-version corpus passes against the
   hosted endpoint with bounded responses and recorded cold/warm measurements;
5. HTTP cache, Cache Storage, and IndexedDB have been compared fairly, with any
   selected persistent cache remaining subordinate to the in-memory LRU;
6. representative monthly cost and a full-artifact cost projection are
   documented with their assumptions and dates; and
7. no crawler/raw database/full build was touched, and no production exposure or
   `bughouse-chess` push occurred without separate approval.
