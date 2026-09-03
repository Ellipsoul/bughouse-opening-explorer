# Packed position graph v2 result — 3 September 2026

## Outcome

The transposition-aware August 2026 graph now has a compact, immutable serving
artifact:

```text
artifacts/opening/full-position-graph-through-202608-v2
```

It retains the v1 build and dataset identity
`68a97678c3df093d243473e0844b373d669ac335`, all position/state/edge IDs,
all outcome counts, and the sorted player postings used by low-latency filters.
The v1 oracle remains intact beside it.

No artifact was uploaded and no Vercel Preview or Production state was changed.

## Measured size

| Component | v1 bytes | v2 bytes | Change |
| --- | ---: | ---: | ---: |
| `positions.bin` | 368,285,184 | 199,487,808 | -168,797,376 |
| `states.bin` | 877,316,330 | 542,341,004 | -334,975,326 |
| `edges.bin` | 812,956,850 | 477,170,325 | -335,786,525 |
| `memberships.bin` | 1,444,865,016 | 963,902,640 | -480,962,376 |
| `games.bin` | 1,959,556,191 | 269,919,200 | -1,689,636,991 |
| `game_offsets.bin` | 53,983,848 | 0 | -53,983,848 |
| unchanged strings and player postings | 930,968,491 | 930,968,491 | 0 |
| new game dictionaries and username tables | 0 | 2,707,022 | +2,707,022 |
| **Total components** | **6,447,931,910** | **3,386,496,490** | **-3,061,435,420** |

The serving artifact is 3.39 GB in decimal units, about 3.15 GiB. This leaves
roughly 1.6 GB below a 5 GB uncompressed Function-package limit before service
source and dependencies are counted.

## What v2 changes

The graph semantics do not change. V2 only changes physical representation:

- position records narrow from 24 to 13 bytes;
- state records narrow from 55 to 34 bytes by deriving loss counts;
- edge records narrow from 46 to 27 bytes by deriving loss counts and a child
  position ID from the retained child state ID;
- a position and its sole state share one posting range;
- a non-root state and its sole incoming edge share one posting range;
- the root never shares with an incoming cycle edge because every game enters
  root implicitly;
- source games use one fixed 40-byte record plus username and small categorical
  dictionaries; and
- `content_hash`, `end_time`, `rated`, and `time_control` are omitted because
  they are not exposed by the browser contract. They remain in the lossless
  local crawler snapshot and v1 oracle.

Chess.com live-game URLs are represented by their numeric game ID and rebuilt
with the fixed `https://www.chess.com/game/live/` prefix. The repacker rejects a
non-Chess.com URL rather than silently losing information.

The 863,028,787-byte placement/label string table is intentionally unchanged.
Compact board encoding remains a separate, higher-risk optimization and is not
needed for the current target.

## Explicit capacity gates

The repacker fails before writing a manifest if current compact fields no longer
fit. Important bounds include:

- fewer than 2^32 positions, states, edges, games, membership entries, username
  IDs, and string/username bytes;
- placement and edge-label lengths below 256 bytes;
- fewer than 256 outgoing edges per state;
- fewer than 65,536 actual endings at one state;
- ratings below 65,535 (`65,535` is the null sentinel);
- fewer than 256 result, source, and provenance-set dictionary values; and
- a UUID parseable as 16 bytes and a Chess.com numeric game ID fitting uint64.

The full v1 scan was comfortably inside every bound: maximum outgoing edge
count 82, ending count 755, placement length 70, edge label length 6, and rating
7,933.

## Validation evidence

The full artifact was produced in 105.935 seconds. Validation checked all eleven
component sizes and SHA-256 hashes, streamed every position, state, edge, game,
and username offset record, and completed in about 11.5 seconds with a measured
peak RSS of 43,794,432 bytes.

The independent parity comparison checked:

- 10,000 deterministic sampled state queries;
- all 6,747,980 browser-visible source-game records;
- popular-white, popular-black, and combined player filters at root; and
- matching build ID, dataset version, counts, roots, and all public query
  responses.

All comparisons passed.

The five-repeat service benchmark measured:

| Case | Median | Observed maximum |
| --- | ---: | ---: |
| unfiltered root | 27.94 ms | 32.55 ms |
| popular white filter | 2,425.99 ms | 2,465.96 ms |
| popular black filter | 2,400.41 ms | 2,419.31 ms |

Responses were byte-deterministic after removing elapsed-time instrumentation.
A fresh process that validated the artifact, ran both popular filters, traversed
the main line, and fetched a source game peaked at 492,519,424 bytes RSS.

## Reproduction and comparison

```bash
.venv/bin/python scripts/repack_opening_position_graph_v2.py \
  artifacts/opening/full-position-graph-through-202608-v1 \
  artifacts/opening/full-position-graph-through-202608-v2

.venv/bin/python scripts/compare_opening_position_graphs.py \
  artifacts/opening/full-position-graph-through-202608-v1 \
  artifacts/opening/full-position-graph-through-202608-v2 \
  --states 10000 --games 10000

.venv/bin/python scripts/benchmark_opening_position_graph.py \
  artifacts/opening/full-position-graph-through-202608-v2 \
  --repeats 5
```

The repacker verifies every declared v1 input size and hash before creating the
v2 directory. It writes `manifest.json` last, so an interruption leaves an
obviously incomplete, non-publishable directory.

## Next release boundary

The exact v2 artifact name is locally allowlisted for the authenticated hosted
service and deterministic chunk transport. That is implementation readiness,
not deployment authorization. Before any upload, refresh the live Vercel plan
and Large Functions limit, build an independent v2 B artifact, compare A and B
component-for-component, stage locally, and obtain explicit Preview approval.
