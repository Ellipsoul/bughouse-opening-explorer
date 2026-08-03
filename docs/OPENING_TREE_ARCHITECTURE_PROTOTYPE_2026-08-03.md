# Opening-tree architecture and representative prototypes — 3 August 2026

This document records the completed architecture/prototype slice that followed
[`OPENING_TREE_EXPLORATION_2026-08-02.md`](OPENING_TREE_EXPLORATION_2026-08-02.md).
It distinguishes demonstrated results from capacity projections and preserves
the remaining gate before any full-corpus index build.

## Outcome

The selected storage architecture is an immutable **prefix-interval packed
trie with sorted game-ordinal postings**. The compact SQLite implementation is
retained as the correctness, inspection, and operational baseline. A zlib-
compressed dense bitmap-posting proxy was measured and rejected.

This selection does not authorize a full-corpus index build. The packed format,
query model, validators, deterministic versioning, and publication boundary
passed the representative slice. The current prototype builder retains all
sample games and logical nodes as Python objects; extrapolating its measured
RAM would violate the production build target. A streaming/external-sort
artifact writer must therefore pass the capacity gate below before a full
build begins.

No Chess.com request or crawler operation occurred. `data/crawler.db` was not
queried or mutated. All corpus work used a disposable restore at
`/private/tmp/bughouse-opening-prototype.vlO7FN/crawler-snapshot.db`, decompressed
from the designated checked backup. Its 15,146,962,944 bytes and SHA-256
`04b5694a288f1b0a966524090e991d70aa695096531933710a0a17f25bb5a5ac`
matched the recovery manifest exactly.

## Frozen semantics

### Inclusion and provenance

The version-1 adapter policy accepts a board when all of these conditions hold:

- TCN is non-empty;
- TCN decodes successfully as exact two-character move tokens;
- `rules` is `bughouse`;
- `initial_setup` is the standard chess initial position;
- exactly one White and one Black participant can be resolved;
- source is `public` or `callback`; and
- decoded length is no more than the defensive 2,048-ply limit.

Both public and callback-only move-bearing boards are included. The checked
snapshot has 7,131,915 accepted public boards and 476 accepted callback boards.
Its longest TCN is 1,155 plies, so no move-bearing board hits the safety limit.
In that initial adapter pass, the only corpus-wide exclusion was 1,063,593
empty-TCN boards. Decode, setup, rules, source, participant-shape, and
safety-limit exclusions were all zero.

An investigation on 3 August 2026 then identified a distinct short-game
population caused primarily by a Bughouse match ending on the other board,
resignation, or abandonment after only a few moves were recorded on this
board. The production build policy therefore adds one result-aware rule:

- exclude a board with **six plies or fewer** unless either resolved
  participant has the exact recorded result `checkmated`.

The exception is intentional. Manual edge-case review confirmed that the short
checkmates are genuine completed Bughouse games, including extremely fast
mates made possible by pieces dropped from the partner board. They are valuable
opening-tree evidence and remain included regardless of line length. Apply the
rule only to the derived opening index; retain every raw board unchanged in
`data/crawler.db`. Count excluded rows under a dedicated provenance reason such
as `short_non_checkmate`, separately from `empty_tcn` and malformed-input
reasons.

Rating zero, rating over 4000, same-account White/Black, callback source, and
partner-link asymmetry are provenance or context, not opening-tree exclusions.
The adapter retains source class, content hash, players, ratings, results,
timing, URL, and bounded anomaly flags. Inclusion never rewrites a raw row.

### Node identity and replay

A node is the exact decoded move prefix. It is never a FEN, placement, board
hash, or transposition class. Different move orders that replay to the same
display position remain different paths. Tests demonstrate that two four-ply
knight cycles with the same resulting FEN remain separately queryable.

The requested prefix is replayed to produce its display FEN. Pocket state does
not split a shared move prefix. Drop tokens remain ordinary navigable edges;
tests navigate a queen drop and verify the replayed board. Display FEN is a
projection only and is not persisted or queried as node identity.

### Terminals

Physical construction stops a line at its first prefix with one distinct
accepted game, or at game end. Every materialized node has a support interval.
A support-one node stores its sole game ordinal explicitly. Game endings are a
separate explicit list, which allows:

- several games with an identical complete line to end at one leaf;
- a game to end at a node that also has continuations; and
- a White, Black, or exact-pairing filtered view to return its sole game before
  the global path becomes unique.

No decode failure or safety-limit outcome is represented as an ordinary
terminal.

## Format-neutral boundary

`CrawlerSnapshotAdapter` opens its input with `mode=ro&immutable=1` and emits
one counted outcome per source row. Accepted outcomes contain an `OpeningGame`;
excluded outcomes contain an exact reason. Storage builders consume only these
records and do not depend on crawler jobs, events, qualification, or HTTP code.

The build identifier is deterministic over the source fingerprint, board UUID,
exact move tokens, and source content hash. A source correction therefore
produces a new immutable version rather than editing a published artifact.

## Short-line investigation and inclusion-policy revision

The original shape pass found 702,991 games ending at internal nodes and
636,971 games belonging to identical complete lines. These figures overlap:
they are not two populations that can be added together. An internal ending is
an actual complete, non-empty TCN that is a strict prefix of another complete
TCN. An identical line means distinct board UUIDs share the same exact TCN;
the UUID primary key prevents duplicate database rows from causing the count.

A second read-only pass over the same checked immutable snapshot established:

- zero accepted games have zero plies; the minimum accepted line is one ply;
- 616,344 games have between one and six plies inclusive;
- 454,906 have exactly one ply, including 288,048 instances of `e4`, 91,867
  of `d4`, and 33,082 of `Nf3`;
- 262,908 short games (42.66%) include result `bughousepartnerlose`;
- 290,593 (47.15%) include result `resigned`;
- 60,885 (9.88%) include result `abandoned`; and
- those three result classes cover 614,386 short games (99.68%).

This supports the two-board termination explanation: the local board record can
end in an ordinary position because the match ended on its partner board. It
also explains the duplicate-line concentration: many distinct games stop after
the same one or two common local moves. Of the original suspicious metrics,
614,823 internal-ending games (87.46%) and 608,273 identical-line games
(95.49%) are at six plies or fewer.

There are 431 short games with a `checkmated` result. Keeping those and
excluding the other short games removes 615,913 boards, or 8.64% of the
initially eligible move-bearing corpus. The resulting production inclusion set
contains 6,516,478 games. Result fields are therefore required build inputs for
inclusion, not merely optional display metadata.

The metrics also distinguish an actual game ending from adaptive support-one
resolution. No actual game ends at the root. A player/seat filter with only one
retained game can nevertheless resolve that game at the empty prefix under the
support-one policy. The eventual API should present that as a selected or sole
game at the current prefix, not as evidence that its TCN ended at the starting
position.

## Full move-prefix shape

The initially eligible 7,132,391-game move-bearing corpus and the revised
6,516,478-game production inclusion set were each sorted by TCN then UUID
through the same immutable snapshot and measured as streams. This was shape
analysis only, not a full index build. The revised pass joined White and Black
results to retain short checkmates, so its elapsed time is not directly
comparable with the original TCN-only pass.

| Metric | Initial move-bearing set | Revised production set |
| --- | ---: | ---: |
| Accepted games | 7,132,391 | **6,516,478** |
| Source plies | 325,470,732 | **324,522,210** |
| Logical nodes / edges | 11,626,980 / 11,626,979 | **11,625,223 / 11,625,222** |
| Relational membership entries | 98,134,927 | **96,570,295** |
| Membership entries per game | 13.76 | **14.82** |
| Nodes per game | 1.63 | **1.78** |
| Games ending at internal nodes | 702,991 | **88,168** |
| Identical complete-line groups | 13,078 | **8,339** |
| Games in identical complete lines | 636,971 | **29,021** |
| Patricia-removable one-child/no-ending nodes | 1,859,979 (16.0%) | **1,860,331 (16.0%)** |
| First terminal depth P50 / P90 / P95 / P99 | 13 / 19 / 20 / 23 | **14 / 19 / 20 / 24** |
| Peak node width | 1,246,015 at ply 13 | **1,246,015 at ply 13** |
| Streaming analysis time | 42.18 seconds | **71.35 seconds** |
| Streaming throughput | 169,088 games/s; 7.72M plies/s | **91,326 games/s; 4.55M plies/s** |
| Streaming peak RSS | 632,782,848 bytes | **632,438,784 bytes** |

An interval per node now replaces 96.57 million repeated membership entries
with 11.63 million node ranges, an 87.96% reduction in that logical row count.
Removing 8.64% of games removes only 0.015% of nodes: the same short prefixes
remain necessary for longer games and the retained short checkmates. Capacity
savings therefore come primarily from per-game metadata, seat postings, and
explicit endings rather than node or edge records.

Patricia compression was explicitly evaluated. Its maximum removable-node
share is 16.0%, before accounting for virtual nodes needed to preserve
move-by-move navigation. It is deferred because interval representation buys a
larger reduction without complicating path navigation.

## Prototype representations

### Compact relational baseline

The SQLite baseline uses dense game ordinals, exact-prefix nodes and edges,
explicit memberships and endings, per-node result aggregates, and independent
covering indexes for White, Black, and exact pairings. System-SQLite query plans
confirmed that each filter begins with its relevant seat/pair index and then
seeks membership by game ordinal and node.

It has the best inspection and startup behavior, but repeats one membership row
and a reverse-index entry for every supported game/node pair.

### Prefix-interval packed trie

The packed candidate stores:

- 36-byte fixed node records with ordinal interval, child range, ending range,
  and optional sole-game ordinal;
- 6-byte move-token/child edge records;
- explicit ending ordinals;
- random-access bounded game metadata;
- independent per-player White and Black sorted ordinal postings; and
- global result postings, ranked over child intervals for branch aggregates.

Two binary searches count a player posting inside a node interval. Exact
pairings intersect the independently sliced White and Black postings. Packed
components are hashed in a deterministic manifest and memory-mapped for reads.

### Compressed bitmap proxy

The alternative bitmap representation zlib-compresses one dense game-ordinal
bitset per seat/player and result. It tests the set-intersection shape without
adding a Roaring dependency. It is not claimed to represent Roaring's chunked
encoding, but it is sufficient to determine whether dense compressed bitsets
are justified by this sparse, mostly single-seat query workload. They are not.

## Benchmark contract

Every candidate used the same immutable source fingerprint and deterministic
source-row sample. The two sizes were rowid modulo 142 (50,215 accepted games)
and modulo 71 (100,475 accepted games), both remainder zero. The larger sample
also reported 14,961 empty-TCN skips and 4,587,370 source plies.

The common query corpus included root, ply-six mid-line, deepest shared line,
missing prefix, global support one, prolific player as White, prolific player
as Black, exact pairing, and sparse White/Black support-one filters. Responses
were serialized identically. “Cold” means a new reader for every query; the OS
page cache was not forcibly dropped. Warm results use one open reader with a
deterministically shuffled 200 repetitions per query.

### Explicit targets

The selected architecture must provide:

- exact-prefix, terminal, ending, replay, and independent-seat correctness;
- projected full artifact no larger than 5 GiB;
- production peak build RSS no larger than 4 GiB;
- full rebuild in less than 60 minutes;
- startup and open-per-query P99 below 250 ms;
- warm P99 below 20 ms for every representative query;
- bounded response below 16 KiB;
- deterministic rebuild, corruption detection, atomic publication, and
  rollback while retaining the previous version; and
- no mutation or operational dependency on the raw crawler database.

### Two-size build and storage results

| Candidate | Games | Build seconds | Final MiB | Peak RSS MiB |
| --- | ---: | ---: | ---: | ---: |
| SQLite | 50,215 | 1.343 | 35.52 | 252.1 |
| Packed sorted | 50,215 | 0.653 | 25.87 | 277.2 |
| Packed bitmap | 50,215 | 1.424 | 26.18 | 277.5 |
| SQLite | 100,475 | 2.991 | 74.09 | 473.1 |
| Packed sorted | 100,475 | 1.370 | 51.37 | 522.8 |
| Packed bitmap | 100,475 | 3.124 | 51.79 | 527.1 |

Doubling accepted games increased packed-sorted bytes by 1.99x and build time
by 2.10x. SQLite bytes grew by 2.09x and build time by 2.23x. The packed-sorted
prototype built 2.18x faster and was 30.7% smaller than SQLite at the larger
point. Bitmap postings were 448,820 bytes larger than sorted postings and made
the build 2.28x slower than packed sorted.

The larger SQLite `dbstat` breakdown was led by game metadata (23,035,904
bytes), membership (13,787,136), the reverse membership index (13,217,792),
node results (5,881,856), UUID index (5,013,504), and nodes (4,513,792).
White, Black, and pairing indexes together occupied 9,261,056 bytes.

The original benchmark remains the fair candidate comparison because every
candidate used its same unfiltered deterministic inputs. A targeted rebuild of
the larger sample under the revised production policy measured the capacity
effect without changing the architecture choice:

| Metric | Original sample | Revised policy |
| --- | ---: | ---: |
| Games | 100,475 | 91,911 |
| Source plies | 4,587,370 | 4,573,999 |
| Nodes | 168,944 | 168,830 |
| Membership entries | 1,068,215 | 1,046,292 |
| Explicit endings | 9,280 | 748 |
| Packed sorted final MiB | 51.37 | **47.52** |
| SQLite final MiB | 74.09 | **70.44** |

Six short checkmates occurred in this deterministic sample and were retained.
This policy-impact rebuild did not repeat latency or build-time measurements;
the original same-input candidate comparisons remain the performance evidence.

### Larger-sample warm latency

Values are P50 / P95 / P99 milliseconds.

| Query | SQLite | Packed sorted | Packed bitmap |
| --- | ---: | ---: | ---: |
| Root | 0.201 / 0.212 / 0.221 | 0.185 / 0.191 / 0.192 | 6.594 / 6.782 / 6.878 |
| Prolific White | 1.263 / 1.315 / 1.344 | 2.089 / 2.126 / 2.308 | 3.174 / 3.236 / 3.308 |
| Prolific Black | 1.309 / 1.360 / 1.382 | 2.192 / 2.229 / 2.298 | 3.277 / 3.340 / 3.490 |
| Exact pairing | 0.248 / 0.264 / 0.273 | 0.374 / 0.394 / 0.399 | 1.765 / 1.828 / 1.888 |
| Filtered support one (White) | 0.045 / 0.048 / 0.049 | 0.021 / 0.023 / 0.023 | 1.062 / 1.096 / 1.104 |

Startup P50/P95/P99 was 0.040/0.058/0.058 ms for SQLite,
8.023/8.069/8.069 ms for packed sorted, and 9.698/9.951/9.951 ms for bitmap.
The largest open-per-query P99 was 1.62 ms for SQLite, 17.36 ms for packed
sorted, and 43.60 ms for bitmap. The largest response was 3,336 bytes.

All candidates clear the latency/response targets at representative scale.
Bitmap postings nevertheless add size and consistently lose the important
root and player-filter paths.

## Capacity projection

The revised projection uses the production-policy full node, edge, membership,
game, and ending counts plus revised larger-sample component bytes. It is not a
full artifact measurement.

- packed sorted: approximately **3.23 GiB** (previously 3.51 GiB);
- SQLite: approximately **5.38 GiB** (previously 5.72 GiB).

The packed estimate conservatively retains the prototype's verbose JSON-lines
game metadata and allows 30 MB for the full posting directory. A later columnar
game-record/string-table layout can reduce this without changing interval or
posting semantics. The SQLite projection scales membership tables and indexes
with the measured 96.57 million production-policy entries rather than game
count alone.

Packed sorted clears the 5 GiB target with about 35% capacity headroom; SQLite
does not. This, the elimination of 96.57 million membership rows, and the 2.18x
representative build advantage justify the packed format's added validator and
reader code. SQLite remains the oracle/fallback because it is operationally
simpler and has excellent query performance.

## Determinism, correction, and publication

Tests demonstrate byte-identical SQLite rebuilds and component-identical packed
rebuilds for identical input. The validators run SQLite `quick_check` or verify
every packed component hash, byte length, node interval, edge range, ending
range, child id, and terminal ordinal before publication.

One representative source correction changed a 53-ply game's content hash and
move sequence to a valid 59-ply line. At 100,475 games:

| Candidate | Corrected rebuild | Publish | Rollback |
| --- | ---: | ---: | ---: |
| SQLite | 3.046 s | 0.127 s | 0.127 s |
| Packed sorted | 1.434 s | 0.083 s | 0.083 s |

Both produced a new deterministic build id, retained the old artifact, switched
an atomic JSON pointer to the corrected version, and switched it back to the
original build id. A test also corrupts a disposable packed edge file and
confirms publication is refused.

The correction strategy for version 1 is deliberately a full immutable
rebuild. No in-place patching or incremental-correction protocol is claimed.

## Temporary bytes and write amplification

Representative output directories contained only the final SQLite file or
packed components plus the small publication pointer. SQLite used journal mode
off and memory temporary storage during these disposable builds; no WAL,
journal, or temporary artifact remained. Packed components were written once
to a new version directory. Thus retained temporary bytes were zero for all
candidates.

macOS reported zero `ru_oublock` deltas for these processes, so it did not
provide a credible physical-write counter. Actual filesystem write
amplification is therefore **not measured**, and the benchmark does not report
the zero counter as evidence of zero writes. Before the full build, the
streaming-writer benchmark must use a reliable per-process/filesystem counter
or explicitly report final bytes as only a lower bound.

## Rejected and deferred options

- **Dense compressed bitmap postings:** rejected. They are larger and slower
  than sorted ordinals for the measured single-seat/range workload. Roaring may
  be reconsidered only if later multi-filter set algebra changes the query
  shape materially.
- **SQLite as selected production format:** retained as baseline but rejected
  for the first full-format choice because the revised component projection is
  5.38 GiB and repeats 96.57 million memberships plus a similarly sized reverse
  index.
- **Patricia physical compression:** deferred. Its 16.0% upper-bound node
  saving is smaller than interval membership elimination and requires virtual
  expansion to keep every move navigable.
- **LMDB or another ordered key/value store:** not prototyped. The packed
  interval format already answers the measured queries directly; an added
  storage engine has no demonstrated requirement.
- **DuckDB/Parquet:** not needed for this slice. SQLite's immutable external
  sort streamed the full shape in 42.18 seconds. They remain valid offline
  analysis tools if later joins or columnar build stages warrant them.
- **Different build/service language:** not warranted yet. Python streamed the
  full shape at 7.72 million plies/s. The demonstrated problem is object
  retention, not decode throughput. A compiled writer is permissible if the
  streaming artifact benchmark exposes a real CPU bottleneck.
- **FastAPI, a frozen API, and Next.js integration:** deliberately not selected
  or changed in this slice. Query records are an internal prototype contract,
  not the production HTTP API.

## Selected next product slice

The next slice is a local vertical explorer over the packed representation. A
thin localhost service will memory-map a representative artifact; the
`bughouse-chess` Next.js client will query that service rather than load the
artifact into JavaScript memory. The same client boundary can later point to a
hosted read service.

Navigation will prototype a budgeted forward neighborhood. A target depth of
five is useful for reducing one-request-per-move latency, but depth is never the
only limit: the revised trie contains approximately 97,057 nodes from the root
through ply five. Every response must include the anchor and its immediate
children, expand deeper high-support continuations only within hard node and
encoded-byte budgets, and return explicit frontier ids wherever expansion was
truncated. Flat versioned node records allow overlapping responses to merge
into a bounded client cache; already visited backward navigation should require
no request.

The prototype will compare per-move fetching, fixed depths, and adaptive
budgeted prefetch on deterministic forward, branching, backtracking, deep, and
filtered traces. It will measure response bytes, local service latency, requests
per move, cache hits, blocked interactions, unused prefetched nodes, and client
render latency before freezing any hosted API contract.

## Remaining gate before a full index

The selected production build shape is:

1. read a checked immutable snapshot;
2. externally sort accepted games by exact move sequence and UUID;
3. assign dense ordinals and stream game metadata/posting runs;
4. construct interval nodes and edges with adjacent-line lookahead;
5. finalize compact posting and game directories;
6. validate every component and provenance count;
7. publish only a new immutable version; and
8. retain the previous version for rollback.

Before building all 6.52 million production-policy games, the format-neutral
adapter and durable measurement script must first implement and count the
`short_non_checkmate` exclusion with tests. The streaming writer must then
repeat the 100k benchmark under that same final policy and demonstrate:

- peak RSS below 4 GiB with a conservative full-scale projection;
- projected/final packed artifact below 5 GiB;
- reliable temporary-byte and physical-write measurements;
- deterministic components across two builds;
- the same query corpus and result bytes as both current prototypes; and
- validator, correction, atomic publication, and rollback behavior.

The full streaming shape pass proves that sorted adjacent-prefix analysis can
stay near 603 MiB. It does not by itself prove that the complete artifact writer
meets the 4 GiB gate.

## Reproduction entrypoints

The implementation is under `bughouse_explorer/opening/`. The durable scripts
are:

```text
scripts/measure_opening_shape.py
scripts/benchmark_opening_prototype.py
scripts/benchmark_opening_correction.py
```

Representative commands require an explicit immutable checked-snapshot path
and new disposable output paths. They do not default to `data/crawler.db`.
