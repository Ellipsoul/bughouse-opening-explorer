# Vercel Large Function Production result — 4 August 2026

## Outcome

The full accepted-game artifact is live in Production through the existing
same-origin frontend boundary. Production metadata reports 6,516,478 accepted
games and dataset version
`1e876810b96364e4bf9f23d49fb509a843783253`. The representative deployment is
retained and remains the bounded rollback target.

No Blob store, database, container, paid plan, new credential, public artifact
route, or browser-side corpus was created. `data/crawler.db` was not opened,
served, modified, or used.

| Boundary | Active deployment | Runtime |
| --- | --- | --- |
| opening service | `dpl_5EwbtsRxMLMcUoVNZksJQAC5A6ns` | Python 3.12, 2,048 MB, 300 s, `iad1` |
| frontend | `dpl_9KkUweLLKcgRDk6vMfmfsGihaRiZ` | Node.js 22, 1,024 MB, 60 s proxy, `iad1` |
| public frontend | `https://bughouse.aronteh.com` | full dataset through `/api/opening-explorer/*` |
| service alias | `https://bughouse-opening-explorer-service.vercel.app` | server-only bearer boundary |
| retained rollback | `dpl_EFQgMysFNBRqQRqZctoMYtp8Pvar` | representative dataset |

The active service Function is 2,018,458,792 bytes after Vercel packaging. Its
output digest is
`prj_BUO6dAAVzaQAhjbFlJ7e5Lt1I2dP/c367a514a3b5fb668bc311ce1675462448e6481e26336f012af3d3de20c81489`.

## Artifact identity

Artifact A was the only upload source. Artifact B remained immutable and had
already proved component identity. No full tree rebuild was run in this slice.

- source snapshot SHA-256:
  `04b5694a288f1b0a966524090e991d70aa695096531933710a0a17f25bb5a5ac`
- accepted games: 6,516,478
- packed components: 2,524,966,683 bytes
- packed components plus `manifest.json`: 2,524,968,549 bytes
- dataset version: `1e876810b96364e4bf9f23d49fb509a843783253`

| Component | Bytes | SHA-256 |
| --- | ---: | --- |
| `edges.bin` | 69,751,332 | `33867afed4a8060b7febafdb2515f0dda90315bc2f77bf0a6241d94325761da3` |
| `endings.bin` | 470,456 | `870ed3e5092d1746baa198e32092aa2f56a224b0b587f221c84e6aeb97a29b88` |
| `game_offsets.bin` | 52,131,832 | `d506bee7d360bc10adc6757b4137f8e17d2828d80b68eeaae09bb9951f9b0ca0` |
| `games.bin` | 1,892,357,989 | `33898a7dd13e34ac8c1c7dfb37551a3452d528e735fe3f1bd3d53f44e9e6aea7` |
| `nodes.bin` | 418,508,028 | `212846f6806a58801d62f34522c0b4b602e2e65c7e05ceb9439057aabb2fda84` |
| `postings.bin` | 78,197,736 | `594ecc0b982ef68e453ce1a88156dd5134ea9d834a6618556f3f8717a53d34c9` |
| `postings.json` | 13,549,310 | `0128cfc462db5c11e9494c0963563fdde64c74b6762f3050a594f61cb2c6e993` |

## Transport and interruption proof

The TDD transport uses deterministic 64-MiB-or-smaller chunks, an exact
allowlist, source and chunk size/SHA-256 validation, a durable acknowledgement
journal, idempotent content-addressed retries, ordered reconstruction, and a
complete artifact validator. Chunks and journals stayed under `/private/tmp`
and outside Git.

The representative interruption rehearsal stopped one in-progress chunk after
8,388,608 bytes. On restart, 22 acknowledged files (1,860,824 bytes) were
reused; the incomplete chunk was retried and the remaining 35,033,817 bytes
were uploaded. A subsequent identical run reused all 28 files and all
36,894,641 staged bytes. Remote reconstruction returned the original component
digests and passed complete validation. Both disposable rehearsal deployments
were removed.

The full staged source contained 64 files and 2,525,091,423 bytes. The initial
upload acknowledged every file with one retry. The runtime-selector correction
produced a 2,525,093,192-byte stage: exact path/size/SHA-1/SHA-256 journal
rebasing reused 62 files and 2,525,066,610 bytes, uploading only two changed
service files (26,582 bytes) with no retry. No ordinary Vercel large-file upload
or `--archive=tgz` path was used.

## Remote materialization and packaging

Vercel CLI 58.5.1 fixed the local stale 500-MB packaging failure. The remote
builder used CLI 58.1.0 on a 2-core/8-GB `iad1` machine. The active Production
build reported:

- 24,600,653,824 free bytes before reconstruction;
- 5,049,937,098 required free-headroom bytes;
- 2,524,968,549 reconstructed and checksum-validated bytes;
- dataset version `1e876810b96364e4bf9f23d49fb509a843783253`;
- `Function exceeds the standard size limit; enabling large functions (beta)`;
- 35 seconds for materialization, validation, dependency packaging, and build;
- about 154 seconds for output deployment, followed by a 2-second build-cache
  creation.

Transport chunks, their manifest, and the materializer were excluded from the
final Function. A byte-count or digest mismatch fails the build before alias
assignment.

## Hosted validation

The protected full Preview first passed the same representative/full oracle and
query budgets. Its 16-case oracle had no failure. The final public Production
proxy was then compared byte-for-byte with the local full artifact for:

- metadata, root and deep direct navigation;
- internal endings and drop-terminal source games;
- White, Black, exact-pair, invalid, and stale filters;
- player autocomplete;
- invalid nodes;
- the 4,000-node and 512-KiB hard caps; and
- local/hosted conditional requests returning `304`.

All 16 Production cases matched status and response body exactly. The sanitized
report is `/private/tmp/full-production-public-oracle.json`, has no filter
values, and has SHA-256
`cb6598fe8d5176228014d0293d677bf97bce16b6cb47caccab0fff7b2085f770`.
Vercel changes some larger response ETags at the gateway, but the proxy returns
and honors its own hosted ETag correctly; the conditional root request was
`304` with an empty body.

Production browser verification found meaningful content, no framework error
overlay, and no page error. The root tree displayed full counts, including
`e4` with 3,930,496 games. Selecting `e4` updated the move list and child tree.
The existing `/` route and two-board viewer still rendered. The only console
output was the pre-existing Firebase App Check throttling warning. The initial
loading state now tells users that cold starts can take up to 20 seconds and
asks them to be patient; the message disappears when the explorer renders.

## Latency and concurrency

The protected Preview benchmark used 20 repetitions per query shape:

| Query | P50 | P95 | P99 |
| --- | ---: | ---: | ---: |
| root | 274 ms | 313 ms | 16,413 ms |
| deep | 140 ms | 204 ms | 229 ms |
| exact pair | 220 ms | 329 ms | 371 ms |
| White | 1,007 ms | 18,084 ms | 33,519 ms |
| Black | 1,201 ms | 17,714 ms | 17,951 ms |
| ending | 170 ms | 244 ms | 255 ms |
| drop | 246 ms | 351 ms | 408 ms |

Direct cold readiness was 16.294 seconds, a separate cold metadata request was
26.735 seconds, and warm readiness was 0.437 seconds. Public Production exposed
the original frontend proxy's 5-second timeout, so the boundary was changed by
TDD to a 30-second upstream timeout and a 60-second Vercel Function duration.
The 500-node/256-KiB defaults and 4,000-node/512-KiB hard caps were unchanged.

After that correction, a genuine public cold metadata request succeeded in
17 seconds. The Production oracle included a 25.901-second cold metadata
request and an 18.282-second cold White-filter request; both returned exact
bodies. A 64-request public root wave returned 64/64 HTTP 200, with P50 3.450 s,
P95 17.511 s, P99/max 18.266 s. The protected service also returned all 200s at
1, 8, 32, and 64 concurrency. Fluid Compute scaled across instances, so the
per-process overload semaphore did not produce a global 503.

Vercel structured logs did not expose per-request CPU, peak RSS, or instance
memory use. Provisioned memory is confirmed as 2,048 MB; the measured full
local process peak remains about 522 MB. Do not present CPU or hosted RSS as
measured.

## Production cutover correction

Two Vercel behaviors mattered during promotion:

1. `vercel promote` created a new Production clone and rebuilt it rather than
   atomically repointing the existing Preview. The first clone lacked the
   deployment-scoped Large Functions build flag and failed at 500 MB.
2. Sensitive values returned by `vercel env pull` are the literal redaction
   placeholder `(Sensitive)`. Injecting that pulled value into a custom API
   deployment created a Function which authenticated only the placeholder.

The safe resolution was to use the Vercel-built Production clone, which binds
the actual server-side project secret without reading or rotating it. The
canonical service alias was moved only after direct warm-up and public proxy
validation. The frontend proxy was freshly deployed so the timeout correction
and current Production environment were bound. No secret was exposed through a
`NEXT_PUBLIC_*` variable or response.

The failed clone, placeholder-token Production candidate, superseded protected
full Preview, and both disposable rehearsal deployments were removed. The
temporary credential directory and its environment/token copies were deleted.
The active full Production deployment and representative rollback were not
deleted.

## Cost and plan limits

The team remains on Vercel Hobby and no paid resource was provisioned. Observed
monetary charge for this slice is therefore $0; Vercel does not provide an
invoice-level per-deployment cost in the CLI or structured logs. This does not
mean the workload consumed zero included usage.

Current official Hobby allowances are 4 active CPU-hours, 360 provisioned
GB-hours, and 1,000,000 invocations. Hobby has no billing cycle; exceeding an
included limit normally pauses the affected feature rather than creating an
on-demand bill. For comparison only, current `iad1` Fluid rates are $0.128 per
active CPU-hour and $0.0106 per provisioned GB-hour. The confirmed 2-GB Function
would therefore correspond to at most about $0.149 per fully active instance
hour under the published rate model. Actual slice CPU and GB-hour consumption
was not exposed, so no invented cost estimate is recorded.

The Large Functions path remains public beta. The ordinary documented Python
compressed package limit is 500 MB; the active 2.018-GB package depends on the
separately enabled 5-GB Large Functions path. The current rollback command may
only move one Production deployment back on Hobby; when Vercel rejected a
deeper rollback, assigning the canonical service alias directly to the retained
representative deployment succeeded.

## Verification and repository state

- opening service: 170 Python tests passed;
- frontend unit tests: 474 passed across 50 files, including all 35
  opening-explorer tests;
- TypeScript and ESLint: passed;
- frontend local and remote Production builds: passed;
- protected Preview oracle: 16/16 passed;
- public Production oracle: 16/16 passed;
- public root concurrency: 64/64 HTTP 200;
- live browser route, navigation, console/page errors, `/`, and two-board
  regression: passed;
- generated chunks, journals, artifacts, credentials, bypass URLs, filter
  values, and raw corpora: absent from Git.

The changes were reviewed as two repository-scoped commits; generated and
sensitive material was excluded before publication.

## Rollback

The immediate bounded rollback is:

```text
vercel alias set dpl_EFQgMysFNBRqQRqZctoMYtp8Pvar bughouse-opening-explorer-service.vercel.app --scope aronteh-projects
```

After rollback, verify the public metadata returns representative dataset
`e1400ceb14e26dc3cd09e93ac1a4630e88c2ac03`. Restoring the full deployment uses
the same alias command with `dpl_5EwbtsRxMLMcUoVNZksJQAC5A6ns` and must again
verify dataset `1e876810b96364e4bf9f23d49fb509a843783253`.

## Recommendation

Keep the full artifact in Production with the representative deployment
retained. The current evidence proves exactness and acceptable warm behavior,
but cold tails of 18–26 seconds remain user-visible and the 5-GB packaging path
is beta. Monitor included Active CPU, provisioned-memory, invocation, error,
and cold-start usage in Vercel. If cold latency or Hobby pauses become common,
evaluate a provider with persistent local disk/process residency before adding
Blob or another paid materialization layer.
