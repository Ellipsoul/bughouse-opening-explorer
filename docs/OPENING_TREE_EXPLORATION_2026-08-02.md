# Opening-tree exploration — 2 August 2026

This document records read-only product exploration performed after recovery
hygiene completed. No crawler request, raw-database mutation, crawler-to-index
adapter, or production opening-tree change was made in this session.

## Outcome

The existing local explorer is a credible behavioral reference, but it cannot
yet consume `data/crawler.db`. Its legacy indexer expects a different `games`
table in `data/games.db`, records a fixed number of plies per game, and has no
explicit terminal-node reference for a position supported by one game.

The next implementation should preserve the demonstrated product behaviours,
not the legacy schema or framework. The indexed seat-filter approach is a
candidate, while transposition merging is not part of the first product. A new
schema, packed immutable format,
embedded key/value store, different build language, or hybrid design is valid
if measurement shows it is the simplest robust option at corpus scale.

Whichever representation wins must introduce a crawler adapter and replace
fixed-depth-only indexing with support-aware termination in a move-prefix trie:

1. treat the exact sequence of decoded moves as node identity, keeping
   transpositions as separate paths;
2. count distinct-game support for each move prefix and retain the membership
   required for filters;
3. collapse a path to an explicit game reference once its prefix support is
   one, while also representing games that end at a still-shared node; and
4. at query time, allow a player-plus-colour filtered branch to terminate
   earlier when its filtered support falls to one.

This is a derived, rebuildable artifact. The raw crawler database remains
unchanged and authoritative.

## Retained local application

The reference application consists of:

- `frontend/`: Vite, TypeScript, and Chessground;
- `bughouse_explorer/indexer.py`: legacy-input replay and fixed-`max_ply`
  position-graph construction;
- `bughouse_explorer/db.py`: derived positions, edges, game facts, metadata,
  indexes, and default aggregates; and
- `bughouse_explorer/server.py`: local FastAPI read service.

The frontend was installed, built, served, and exercised locally against a
disposable 12-game synthetic legacy database outside the repository. The build
completed successfully with Vite 5.4.21. The page demonstrated:

- branch continuations with counts and result bars;
- move navigation, reset, board flip, and FEN lookup;
- example-game links;
- minimum-rating and minimum-game filters; and
- independent exact username filters for White and Black.

Filtering the synthetic root for `Alice` as White changed the continuation
counts and returned only games in which Alice occupied that seat. Query-plan
inspection showed that the White and Black paths use `idx_meta_white` or
`idx_meta_black` first, then seek facts through
`idx_facts_game(game_id, parent_id)`. That is the right basic direction for
the critically important player-plus-colour filter.

The retained application can be run when a compatible derived database exists:

```bash
cd /Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer
cd frontend && npm ci && npm run build && cd ..
./start-server.sh /absolute/path/to/compatible-opening-index.db
```

Then open `http://127.0.0.1:8000`. Do not pass `data/crawler.db` to this command:
the current reference server expects the legacy/derived schema, not the crawler
schema. The separate Vite development server is available with `npm run dev`
and proxies `/api` to port 8000.

`npm ci` reported three dependency audit findings (one moderate and two high).
They were not automatically changed during this exploratory session. Review
them when product implementation begins rather than applying an unmeasured
dependency rewrite as part of data-index work.

## Existing index strengths and gaps

The existing schema already provides several useful ideas:

- canonical positions use the four-field position FEN and a compact BLAKE2
  lookup hash, with the full FEN checked after a hash match;
- transpositions converge on the same position;
- `game_facts` records at most one fact for a distinct
  `(position, move, game)` occurrence;
- `games_meta` keeps both usernames, ratings, result, URL, time control, and
  end time;
- default unfiltered branches use a precomputed `move_agg`; and
- username queries drive from an indexed White or Black seat instead of
  scanning every fact at a busy opening position.

The gaps for the requested product are:

- the input is the old `games` table, not the crawler schema;
- all games are truncated at one fixed `max_ply` (40 by default);
- there is no global distinct-game support table for positions;
- there is no explicit terminal position-to-game reference;
- the games endpoint finds examples through outgoing `game_facts`, so a child
  with no outgoing edge cannot by itself expose the sole game; and
- the complete username list is downloaded, whereas the production API should
  use bounded prefix search over the much larger crawler identity set.

None of these tables or endpoints is a compatibility requirement. The legacy
application had a much smaller workload and is useful mainly for recovering
behavioural requirements and constructing a baseline benchmark.

## Settled semantic model: move-prefix trie

The first product will use a **move-prefix trie**. A node is identified by the
exact sequence of moves on this board from the start. Two move orders that
reach the same visible board remain different nodes and different navigable
lines. This matches the expected opening-tree interaction and makes support-one
termination unambiguous.

The board shown for a node is a projection obtained by replaying that exact
prefix. Visible piece placement, side to move, castling, and en-passant state
support display and move labels. Pocket holdings remain meaningful Bughouse
context, but they do not identify nodes or split paths: games with the same
move prefix share one trie node even when their pockets differ. Holdings may
later be exposed as bounded node annotations or distributions if reconstructable
and useful. Drop moves remain first-class trie edges, so a user can navigate
paths containing piece drops and see the resulting pieces on the board.

The retained engine's “no pocket; drops are placements” replay is therefore
potentially reusable as a display projection, after verification, but its
four-field FEN must not identify or merge trie nodes. FEN lookup is inherently
ambiguous in this model because multiple prefixes may display the same board;
it should be deferred, return multiple matching lines, or require path context.

Holdings-aware single-board merging and a synchronized two-board state graph
are explicitly deferred research, not requirements for the first explorer.

## Terminal-node semantics

For the first implementation, a prefix is unique when exactly one distinct
accepted board has that exact decoded move prefix. A globally unique prefix is
a safe physical stopping point because every longer prefix belongs to the same
game. A player-plus-colour filtered view can become unique earlier; the API
should return that sole filtered game rather than forcing navigation to the
deeper global terminal.

The build does not inherently require position replay to find branch points.
Because TCN encodes every ply in a fixed two-character token, a candidate build
can sort accepted move strings and derive shared prefixes from adjacent strings.
A radix/Patricia trie can likewise keep unique suffixes compressed and split
them only when another game shares part of the prefix. Compare these approaches
with ordinary streaming count construction; do not assume the earlier two-pass
position-support algorithm remains necessary.

The terminal payload should contain a stable board UUID or internal game id and
the display fields needed for a bounded game link. A concrete schema should be
chosen only after the representative benchmark, but the first design must make
terminal membership explicit rather than inferring it from an outgoing edge.

If several games have identical complete move strings, their shared leaf holds
multiple game references. If one game ends at a prefix another game continues,
the node holds both the ended-game reference and outgoing edges. The build
should retain a defensive decode/replay limit and count/report any failure or
safety truncation; it must not silently convert a safety cap into an ordinary
terminal.

## Exploratory uniqueness measurements

Two deterministic, full-rowid-range samples were replayed from an immutable
read-only connection to `data/crawler.db`. These were in-memory analyses of the
legacy transposition-merging position key, not move-prefix tries or derived-index
builds, and they made no database changes.

| Sample | Games | Full plies | Mean first-unique ply | P50 | P90 | P95 | Adaptive retained plies | Retained share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| about 10k | 9,978 | 457,022 | 10.19 | 10 | 15 | 17 | not retained as a durable build | 20.7% |
| about 50k | 49,872 | 2,274,749 | 11.87 | 12 | 17 | 18 | 545,418 | 24.0% |

In the 49,872-game sample, 45,040 games reached a globally unique position and
4,832 did not. The maximum first-unique ply was 29. Median position support at
sampled depth fell from 3,618 games at ply 2, to 105 at ply 6, to 4 at ply 10,
and to 1 at ply 12.

These figures support adaptive termination generally but must not be used as a
capacity forecast for the chosen move-prefix trie. Prefix support does not merge
transpositions and needs a fresh measurement. The next slice can calculate
exact unique-prefix depth cheaply from sorted TCN strings before committing to
an on-disk layout. A representative on-disk build must still measure actual
size, write amplification, query latency, and depth distribution.

The raw corpus contains 325,470,732 valid plies across those 7,132,391 boards.
Replaying the moves is tractable on this hardware; the likely dominant risk is
the size and write pattern of per-game membership needed for arbitrary filters.
That remains a hypothesis until the representative SQLite build is measured.

## Open architecture design space

The next slice should compare representations from first principles rather
than merely tuning `game_facts`. At minimum, consider these families:

### Relational embedded baseline

A redesigned SQLite index remains the operational baseline: compact integer
ids, covering indexes, bulk-load order, explicit terminal membership,
precomputed unfiltered aggregates, and `WITHOUT ROWID` tables where composite
keys actually benefit. SQLite documents `WITHOUT ROWID` as a clustered-primary-
key optimization that can reduce space or improve speed for suitable schemas;
it is an optimization to measure, not a blanket rule. See the official
[SQLite `WITHOUT ROWID` documentation](https://www.sqlite.org/withoutrowid.html).

### Prefix-interval packed trie

Sort accepted games lexicographically by their fixed-width TCN move-token
sequence, using UUID as a deterministic tie-breaker, and assign a dense game
ordinal in that order. Every trie prefix then owns one contiguous ordinal
interval `[start, end)`. A packed node can store that interval and an offset into
sorted child edges rather than one membership row for every game at every node.

For a player-as-White or player-as-Black filter, store that player's sorted
game ordinals. Two binary searches give the number of that player's games in a
node interval; cardinality one identifies the sole game directly. Exact pairings
can intersect the two seat-specific posting lists. This interval invariant may
remove most of the `game_facts`-style duplication while preserving efficient
filtered terminals, so it is the leading non-relational candidate to benchmark.

A rebuild can produce versioned arrays with compact node and edge records,
CSR-style adjacency offsets, columnar game metadata, and memory-mapped reads.
Fixed-width TCN tokens permit direct common-prefix comparison before board
replay; board projections or labels can then be generated only for retained
branch nodes and requested paths. A radix or Patricia representation may also
compress one-child runs.

This design costs custom format, rank/lookup, validator, tooling, and migration
code. It must demonstrate a material end-to-end advantage over compact SQLite,
including result aggregation and corrections, not only a smaller adjacency
file.

### Bitmap-posting hybrid

Assign dense integer game ids and represent the games supporting an edge,
node, player-as-White, player-as-Black, outcome, or optional rating bucket as
compressed posting sets. A filtered branch becomes set intersection plus
cardinality; cardinality one directly yields the sole game id. Roaring bitmaps
are specifically designed for compressed integer sets and fast intersection,
union, and difference, making this a strong candidate for the critical
player-plus-colour query. Measure bitmap duplication and serialization cost at
deep, low-support nodes. See the
[RoaringBitmap project](https://github.com/RoaringBitmap/RoaringBitmap).

This can be combined with SQLite metadata or a packed adjacency file rather
than becoming a separate database server. It should also be compared with the
simpler sorted-ordinal posting lists implied by the prefix-interval design;
Roaring may win for repeated multi-filter intersections but is not automatically
needed for one player plus one interval.

### Embedded ordered key/value store

LMDB or another mature embedded ordered store could map a compact node key to
a serialized branch record and keep named posting/index maps. LMDB offers
memory-mapped ordered reads and cheap read transactions, but requires explicit
map-size and single-writer operational discipline. Compare it only if the
packed-value model is compelling; replacing SQL is not itself an optimization.
See the [LMDB Python documentation](https://lmdb.readthedocs.io/en/latest/).

### Analytical and server engines

DuckDB/Parquet may be useful in the offline build and measurement pipeline,
where full scans and columnar analysis dominate. PostgreSQL, ClickHouse, a
graph database, RocksDB, or a service written in Rust/Go remain permissible
production candidates, but each adds deployment or implementation cost. Do not
select one by category reputation. First demonstrate that the embedded
baseline cannot meet the measured size, rebuild, latency, concurrency, or
update target.

FastAPI and Python are similarly not contractual. Python can remain the
orchestrator while a measured replay or bitmap hotspot moves to a compiled
component. A framework or language change needs an end-to-end benchmark and an
operational reason, not only a microbenchmark.

## Fair comparison contract

Candidate prototypes must consume the same deterministic accepted-game sample,
use the same node semantics and terminal policy, and answer the same query
corpus. Compare at least:

- cold and warm root, mid-line, deep, missing, global support-one, and filtered
  support-one queries;
- unfiltered, player-as-White, player-as-Black, and exact White-versus-Black
  filters, including prolific and sparse players;
- build throughput, peak RAM, temporary and final bytes, write amplification,
  startup time, response bytes, and P50/P95/P99 latency;
- deterministic rebuild hashes or logical equivalence, corruption detection,
  atomic publication, rollback, and deletion/replacement of a corrected game;
- implementation complexity, dependency risk, debugging/inspection quality,
  deployment burden, and the ability to evolve the schema; and
- extrapolation error by running at more than one sample size.

Use the simplest design that clears explicit targets with capacity headroom.
No candidate wins merely by producing the smallest file or fastest isolated
lookup.

## Engineering rules for the derived product

- Correct node identity and query semantics come before storage optimization.
- The raw snapshot is immutable input; the index is disposable output.
- Builds are deterministic, restartable, observable, versioned, and validated.
- Inclusion, exclusions, decode failures, and safety truncations are counted.
- Readers see one immutable version; publication is atomic and rollbackable.
- Common queries are bounded; pathological filters cannot trigger full export.
- Measurements use representative data and reproducible query fixtures.
- Complexity must buy demonstrated capacity, latency, or operational safety.
- Component boundaries keep the crawler adapter, replay semantics, storage
  writer, validators, and read API independently testable.
- Full-corpus construction waits until semantics and representative benchmarks
  pass.

## Decisions for the implementation slice

The next session should make and document these decisions before a large build:

1. Inclusion policy and provenance: start from non-empty, successfully decoded
   TCN; explicitly decide whether the 561 callback-only boards are included;
   count empty TCN and every other exclusion by reason; never delete raw rows.
2. Node identity: use the exact decoded move prefix. Keep transpositions
   separate. Replay the prefix for board display; pocket differences do not
   split a shared prefix, and drop moves remain ordinary navigable edges.
3. Terminal contract: define global and filtered support-one responses,
   end-of-game terminals, game references, and safety-truncation disclosure.
4. Filter shape: make White and Black separate indexed dimensions and benchmark
   exact player-plus-colour branch/support queries at root and deep nodes.
5. Storage shape: benchmark a compact relational baseline against at least one
   materially different candidate. The prefix-interval packed trie is the
   leading alternative; compare sorted ordinal lists with bitmap postings for
   player-plus-colour set intersection.
6. Build shape: compare sorted-prefix/radix construction with streaming count
   construction using a checked raw snapshot, never the live crawler database.
7. Benchmark ladder: begin with a deterministic representative subset, record
   accepted/skipped counts, plies/s, first-unique distribution, distinct
   prefixes by depth, branching, identical complete lines, games ending at
   internal nodes, tables/indexes, WAL/temp/RAM/final bytes, and cold/warm
   filtered and unfiltered latency.
8. Publication boundary: version policy, source watermark, and derived schema;
   validate before publishing; keep the browser on bounded branch responses.

## Copy-ready prompt for the fresh session

Use [`OPENING_TREE_SLICE_PROMPT.md`](OPENING_TREE_SLICE_PROMPT.md). It is the
canonical copy-ready prompt; keep design details in this exploration record so
the prompt can stay focused on execution boundaries and gates.
