# Local opening-explorer vertical prototype — 3 August 2026

This document records the local vertical slice built after
[`OPENING_TREE_ARCHITECTURE_PROTOTYPE_2026-08-03.md`](OPENING_TREE_ARCHITECTURE_PROTOTYPE_2026-08-03.md).
It separates demonstrated results from remaining gates. No Chess.com request,
crawler operation, production deployment, or read of the live
`data/crawler.db` occurred.

## Outcome

The local vertical boundary is implemented:

```text
explicit checksum-verified immutable snapshot
    -> external-sort streaming packed writer
    -> validated immutable packed-prefix-interval-v2 artifact
    -> loopback-only memory-mapped FastAPI experiment
    -> local-flagged /opening-explorer Next.js page
```

The retained representative artifact is ignored by Git at:

```text
artifacts/opening/representative-mod71-v2-a
```

Its dataset/build id is
`e1400ceb14e26dc3cd09e93ac1a4630e88c2ac03`. It contains 91,911 accepted
games, 168,830 nodes, 168,829 edges, and 748 explicit ending references. The
browser boundary returns bounded JSON only; it never receives this directory,
SQLite, the complete tree, raw payloads, or the username corpus.

The full build was deliberately not run. All measured memory, size,
determinism, validation, correction/publication, and temporary-capacity
properties are promising, but reliable physical-write amplification remains
unmeasured: macOS returned a zero `ru_oublock` delta in all four final builds.
The scripts report that counter as unreliable and retain logical temporary
plus final bytes only as a lower bound. This is the exact remaining full-build
gate.

## Source and policy

The source was restored to a new disposable path from the designated checked
backup
`crawler-post-qualification-20260802.db.zst`. The compressed stream passed
`zstd --test`, its SHA-256 was
`90bc1778829eaf52bab881e0b02947e1635320a691f889330716635d94094872`,
and the read-only restored SQLite file repeated the documented recovery record:
`quick_check=ok`, zero foreign-key and qualification/fixed-window violations,
no active or pending work, and closure ready. The uncompressed snapshot
SHA-256 was
`04b5694a288f1b0a966524090e991d70aa695096531933710a0a17f25bb5a5ac`.

Adapter policy `opening-adapter-v2-short-non-checkmate` now:

- emits `short_non_checkmate` for a game of six plies or fewer when neither
  exact participant result is `checkmated`; and
- retains a short game when either exact participant result is `checkmated`.

Both the adapter tests and durable shape/build entrypoints use this policy.
The 91,911-game sample counted 14,961 `empty_tcn` and 8,564
`short_non_checkmate` skips. The 186,009-game sample counted 30,365 and 17,796
respectively.

## Streaming writer

The writer retains no all-game or all-node Python graph. It:

1. stages accepted adapter records in an explicit disposable SQLite external
   sort keyed by exact TCN bytes and UUID;
2. assigns dense ordinals while streaming sorted identical-line groups;
3. retains only the previous/current/next line summary and active trie path;
4. stores temporary node/edge/posting runs on disk;
5. writes the selected 36-byte nodes, 6-byte edges, endings, sorted postings,
   and offsets deterministically; and
6. validates hashes, record/range integrity, then supports the existing atomic
   publication pointer and rollback boundary.

Game metadata changed from verbose JSON lines to independently zlib-compressed,
offset-addressable JSON records (`zlib-json-v1`). This keeps bounded lookup by
ordinal and explicit provenance while avoiding a process-wide metadata parse.
The old v1 reader remains supported.

### Final repeated builds

| Measure | Modulus 71 A / B | Modulus 35 A / B |
| --- | ---: | ---: |
| Accepted games | 91,911 / 91,911 | 186,009 / 186,009 |
| Nodes / edges | 168,830 / 168,829 | 339,858 / 339,857 |
| Build seconds | 8.30 / 8.53 | 15.52 / 15.58 |
| Peak RSS bytes | 61,440,000 / 61,390,848 | 71,647,232 / 71,352,320 |
| Temporary bytes | 52,551,680 / identical | 106,631,168 / identical |
| Final bytes | 36,782,672 / identical | 73,782,864 / identical |
| Projected full bytes | 2,607,886,682 | 2,584,844,873 |
| Physical-write bytes | 0, unreliable | 0, unreliable |

Every component hash was identical across each repeated pair. The build id,
node/edge/endings counts, skip counts, component bytes, and validator result
were also identical. The larger build processed about 11,940–11,982 games/s.

A representative immutable correction changed one selected game's content
hash without editing the original version. The corrected rebuild took 8.41
seconds and produced build id
`841440efc3bcec7e942682d9faa3f6e04440a7be`. Validated atomic publication took
92.83 ms; rollback took 91.35 ms and restored original build id
`e1400ceb14e26dc3cd09e93ac1a4630e88c2ac03`. Both version directories remained
intact.

At modulus 71, compressed random-access metadata is 26,687,930 bytes versus
39,734,192 bytes for JSON lines, a 32.8% reduction. Total artifact bytes fell
from 49,828,934 to 36,782,672, a 26.2% reduction. At modulus 35, metadata fell
from 80,424,849 to 54,015,867 bytes and the artifact from 100,191,846 to
73,782,864 bytes.

## Memory-mapped read service

`bughouse_explorer.opening.service` validates every manifest component before
opening read-only mappings. Startup does not parse game metadata or posting
values into expanded objects. The current JSON posting directory is parsed;
replacing it with a packed searchable directory remains a worthwhile full-scale
startup-RAM refinement, but its representative process cost was bounded.

The experimental operations are:

- `GET /api/meta`;
- `GET /api/nodes/{node_id}/neighborhood`;
- `GET /api/nodes/{node_id}/games`; and
- `GET /api/players?prefix=...`.

Every response identifies the dataset version. Stale versions, invalid node
ids, invalid filters, and requests beyond the 4,000-node/512 KiB hard caps fail
explicitly. The service binds only `127.0.0.1`; CORS permits only local port
3000 origins.

Neighborhoods always include the anchor and every immediate child, return flat
nodes/edges and a replayable ancestor path, prioritize deeper support, separate
structural records from filter overlays, cap games independently, and mark all
truncated boundaries as frontiers. Actual endings and support-one resolution
remain separate fields.

### Service measurements

The initial 2,000-node/256 KiB candidate default took 43–53 ms on representative
root queries because it performed work later removed by the byte cap. A
measured 500-node default with the same byte target was therefore selected;
the hard limits remain 4,000 nodes and 512 KiB.

On 50 warm repetitions over the v2 representative artifact:

| Query | P50 / P95 / P99 ms | Nodes | Encoded / zlib bytes |
| --- | ---: | ---: | ---: |
| Unfiltered root | 4.74 / 5.26 / 6.35 | 500 | 173,244 / 20,596 |
| Player as White | 6.93 / 7.25 / 7.86 | 500 | 151,563 / 16,416 |
| Player as Black | 7.16 / 7.45 / 7.70 | 500 | 150,593 / 16,237 |
| Exact pair | 2.99 / 3.16 / 3.21 | 500 | 147,782 / 15,472 |

Startup was 101.52 ms and measured incremental peak RSS was 10,338,304 bytes.
Responses were deterministic after removing the elapsed-time observation.
All ordinary responses were below the configured hard byte/node caps.

The benchmark also exercised an internal actual ending and a retained
five-ply checkmate whose final token is the pawn drop `=1`. Node 13,983 returned
two explicit actual endings, and both bounded game records carry Black result
`checkmated`.

## Prefetch comparison

The same seven-node popular mainline trace was used for each strategy:

| Strategy | Requests | Unique cached nodes | Uncompressed / compressed bytes | Unused prefetched nodes |
| --- | ---: | ---: | ---: | ---: |
| One request per move | 7 | 165 | 63,695 / 10,533 | 158 |
| Fixed depth 1 | 6 | 143 | 55,519 / 9,208 | 136 |
| Fixed depth 3 | 2 | 2,026 | 656,944 / 69,151 | 2,019 |
| Fixed depth 5, hard caps | 2 | 2,385 | 776,389 / 83,640 | 2,378 |
| Adaptive depth 5, 500 nodes | 2 | 999 | 337,843 / 38,122 | 992 |
| Browser completeness policy, adaptive depth 5 | 2 foreground + 0 idle | 999 | 337,843 / 38,120 | 992 |

Adaptive prefetch met the “fewer than five requests” hypothesis while returning
about half as many unique nodes and compressed bytes as fixed depth five. It
still prefetched far more nodes than the short trace used, so idle refill and
LRU eviction telemetry remain important rather than being treated as solved.

The original simulator counted a cached next edge as sufficient even when the
selected node's move list was only partial. Live testing exposed the mismatch:
the board rendered from cache, but each popular move scheduled a background
frontier refill. Deeper service traversal now prioritizes a high-support parent
and admits all of that parent's immediate children as one atomic group when the
group fits both budgets. Byte-budget trimming also stops only at group
boundaries. The additional browser-policy simulation requires complete move
lists at every visited node; on the same trace it records two foreground
responses and no idle response.

## Next.js boundary

The new route is implemented only under:

```text
app/opening-explorer/page.tsx
app/components/opening-explorer/
app/api/opening-explorer/[...path]/route.ts
```

It imports the existing `ChessBoard` only as a low-level visual primitive and
implements feature-owned TCN replay, drop handling, path/cache/filter state,
HTTP access, lazy examples, and instrumentation. It does not modify or import
viewer controllers, replay state, analysis state, move trees, match navigation,
or existing URL state. The `/` route and its two-board components were not
changed.

The route, sidebar link, and proxy are now present in every build after the
successful representative Production trial. Browser requests use the
same-origin `/api/opening-explorer/...` proxy. The proxy permits only the four
read-only explorer operation shapes and uses the server-only
`OPENING_EXPLORER_SERVICE_URL` (default `http://127.0.0.1:8765`). Development
permits only a loopback HTTP upstream; hosted origins require HTTPS, an exact
server-side allowlist entry, and a bearer credential. It forwards responses
without transforming the versioned service contract.

The client:

- caches structures by `(dataset_version,node_id)` and overlays by normalized
  White/Black filter;
- uses a 5,000-node LRU while pinning the current path and every cached
  immediate move list along that path;
- renders cached children immediately and makes backward breadcrumbs local;
- deduplicates identical HTTP requests;
- keeps differently aborted callers independent so a React development remount
  cannot reuse an already-aborted request;
- uses abort controllers plus a navigation generation so stale responses
  cannot update the selected board;
- refills frontiers during idle time;
- loads game metadata only on request; and
- replaces stale frontier markers when a later response completes a node and
  marks a parent incomplete if one of its children is evicted;
- exposes separate foreground and idle-prefetch neighborhood request counts,
  plus byte, cache hit/miss, returned/used/evicted node, frontier-stall, and
  click-render metrics.

## Commands

Build a representative version only from an explicit restored snapshot whose
checksum has already been independently recorded:

```bash
.venv/bin/python scripts/build_opening_streaming.py \
  /absolute/checked/crawler-snapshot.db \
  artifacts/opening/representative-mod71-v2-a \
  --temporary-directory /absolute/disposable/opening-build-temp \
  --snapshot-sha256 04b5694a288f1b0a966524090e991d70aa695096531933710a0a17f25bb5a5ac \
  --sample-modulus 71 \
  --result /absolute/new/result.json
```

Start the validated loopback service from the opening-explorer repository:

```bash
.venv/bin/python -m bughouse_explorer.opening.service \
  artifacts/opening/representative-mod71-v2-a \
  --port 8765
```

Start the local Next.js experiment from `bughouse-chess`:

```bash
OPENING_EXPLORER_SERVICE_URL=http://127.0.0.1:8765 \
npm run dev
```

Then open `http://localhost:3000/opening-explorer` or use the accessible
`Opening explorer` sidebar icon.

Reproduce the service/prefetch benchmark:

```bash
.venv/bin/python scripts/benchmark_opening_service.py \
  artifacts/opening/representative-mod71-v2-a \
  --repeats 50 \
  --result /absolute/new/service-benchmark.json
```

## Verification and remaining blocker

Demonstrated in this session:

- opening-explorer Python suite: 114 passed;
- Next.js unit suite: 451 passed;
- Next.js TypeScript/ESLint: passed;
- Next.js production build: passed (after permitting its existing Google-font
  downloads);
- feature tests cover the flag, disabled route/proxy, loopback-only forwarding,
  sidebar link, one-board cached navigation, drop replay, LRU/filter keys,
  signal-aware HTTP deduplication, native-fetch receiver binding, and bounded
  idle frontier refill;
- deterministic representative build pairs and packed validation passed; and
- final `git diff --check` passed in both repositories, including the durable
  documentation updates.

The later live retry obtained loopback permission and reproduced the initially
reported unavailable page. FastAPI metadata and CORS were healthy. The browser
failure was an `Illegal invocation`: the client stored native `fetch` as a
class field and invoked it with the API instance as its receiver. The repair
binds the call to the browser global, keeps abort deduplication signal-aware,
and routes local browser traffic through the same-origin proxy.
Both an isolated browser and the user's Chrome then loaded dataset
`e1400ceb14`, rendered the single board and 91,911-game root, and navigated the
cached `e4` continuation. That navigation also revealed and fixed a repeated
idle-frontier refill loop; the final live deep-link emitted one bounded
neighborhood request and no continuing requests after settling. The full
cancellation/filter/back-forward browser matrix remains follow-up evidence
rather than a claimed pass.

A same-day frontend quality-of-life pass removed raw TCN tokens from display,
sorted continuations by descending support, added Up/Down selection plus
Left/Right cached navigation, and replaced verbose result labels with
White-win/draw/Black-win bars. At a 1225 by 768 browser viewport, the document
height remained 768 pixels while the independently scrolling move pane measured
341 client pixels over 1,317 content pixels. A direct visit to sole-game leaf
node 26 loaded one bounded metadata record and displayed both players plus the
source Chess.com URL. The frontend unit suite passed 455 tests, typecheck and
ESLint passed without warnings, and the production build passed.

A later backtracking regression showed that LRU pressure could retain an
ancestor node while evicting most of its children, leaving a silently partial
move list on return to Start. Regression coverage now pins cached immediate
move lists for the visited path and retains a completeness-triggered bounded
refetch as a fallback. Frontier state is replaced, rather than accumulated,
across overlapping responses. The service's atomic parent expansion fixes the
related one-background-refill-per-popular-move behavior described above. The
full Python suite passed 115 tests and the frontend suite passed 457 tests;
TypeScript, ESLint, and the production build also passed.

No full build is authorized until reliable physical-write measurement is
complete and recorded.
