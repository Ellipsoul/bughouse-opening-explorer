# Opening Position Graph Refactor — 1 September 2026

## Outcome

The opening explorer now has a transposition-aware graph contract. The old
`packed-prefix-interval-v2` reader remains available as a rollback reader, but
new artifacts use `packed-position-graph-v1`. The production builder replays
every accepted game to its recorded end, then materializes its path only through
the last globally shared placement plus one source edge.

This change does not publish or deploy an artifact. Publication remains a
separate operational decision after the full local artifact has validated.

> **3 September storage amendment.** `packed-position-graph-v1` remains the
> lossless semantic oracle and rollback format. The active local serving
> candidate is the query-equivalent `packed-position-graph-v2` representation
> documented in
> [`PACKED_POSITION_GRAPH_V2_RESULT_2026-09-03.md`](PACKED_POSITION_GRAPH_V2_RESULT_2026-09-03.md).
> The compact artifact is 3,386,496,490 component bytes. It has not been
> uploaded or deployed.

## Semantic contract

There are three distinct identities:

1. **Position node** — the piece-placement field of FEN, including piece colour.
   Move order, side to move, castling rights, en-passant target, ply, and parent
   are not part of node identity.
2. **Rules-state occurrence** — a position node plus side to move, castling
   rights, and en-passant target. Navigation is anchored to this identity so a
   merged node never offers moves from an incompatible history.
3. **Directed edge** — parent state, exact two-character TCN token, and child
   state. Edge IDs, not child IDs, identify continuation rows and source games.

The graph can have multiple parents, repeated nodes, repeated states, and
cycles. The browser owns the history by which it arrived. The service does not
invent a canonical parent path.

## Counting contract

- Position support is the number of distinct accepted games that reach the
  placement at least once.
- State support is the number of distinct accepted games that reach that rules
  state at least once.
- Edge support is the number of distinct accepted games that traverse that
  edge at least once.
- A game that repeats a node, state, or edge contributes once to that object's
  support.
- Different outgoing edges can contain the same game, so branch supports are
  not required to sum to state support.
- An ending belongs to the exact final state. It is independent of whether the
  same state also has outgoing edges in other games or earlier in that game.
- Result counts are stored as White win, draw, or White loss. Black wins remain
  the residual display category.

The former “stop at first distinct support one” policy is removed. A unique
line can later re-enter a shared position. The production policy is therefore
`last-shared-placement-plus-one-or-game-end-v1`:

1. A first pass externally sorts distinct `(placement identity, game ordinal)`
   records and records placements reached by at least two distinct games.
2. A second pass fully replays each game, finds its last shared placement, and
   materializes every edge through that placement plus one outgoing source edge.
3. If the game ends first, its real ending is materialized. An omitted tail does
   not create a false ending at the materialization frontier.

This retains a support-one bridge of any length when it later reconnects to
shared play. It drops only the tail that the complete first pass has proven
cannot reconnect. Repeated visits by one game count once during discovery.

## Packed artifact

`packed-position-graph-v1` contains:

- `positions.bin` — placement string range and distinct-game membership range;
- `states.bin` — position ID, outgoing edge range, state/end membership ranges,
  outcome counts, side-to-move bit, castling bitmask, and en-passant square;
- `edges.bin` — child position/state IDs, TCN token, display-label range,
  membership range, and outcome counts;
- `memberships.bin` — sorted uint32 game ordinals for positions, states, edges,
  and endings;
- `strings.bin` — each placement once plus edge display labels; states do not
  duplicate placement strings;
- compressed game metadata and per-seat player postings; and
- a checksummed manifest with the source fingerprint and all semantic policy
  versions.

Stable 160-bit BLAKE2 identities order positions and states. SQLite triggers in
the streaming builder turn a hash collision, non-deterministic label, or one
state/token mapping to multiple children into a hard build failure. Both passes
must produce the same accepted count, skip accounting, content, and order digest
before a manifest is written. The production manifest declares
`skip-unreplayable-source-game-v1`: a source TCN that cannot be converted into a
deterministic board sequence is excluded under the explicit
`position_replay_error` counter in both passes. Structural or identity conflicts
among replayable games still abort the build.

## Read API

Metadata adds `root_state_id`. A neighborhood request supplies both `node` and
`state_id`; the service rejects mismatched pairs.

Neighborhoods return separate `nodes`, `states`, and `edges`, plus separately
cacheable `node_overlays`, `state_overlays`, and `edge_overlays`. Expansion is
cycle-safe. Parent move lists are admitted atomically, and response-size
trimming keeps a complete prefix of expansions under the byte cap.

Source-game lookup is `/api/edges/{edge_id}/games`. Looking up examples by
child node would be ambiguous after a transposition and could return a game
that never traversed the selected continuation.

## Browser behavior

- The cache keys outgoing edges by edge ID under a parent state. Two edges that
  reach the same child are both retained.
- The board renders the state FEN returned by the service instead of replaying
  an assumed intrinsic node prefix.
- Navigation appends `{edge, node, state, token, label}` to client-owned
  history. Repeated node/state IDs remain valid history entries.
- Back navigation slices that history, so cycles do not require server ancestry.
- URLs include both `node` and `state`. A refreshed deep link can restore the
  board and continuations, but only in-session navigation has the full arrival
  breadcrumb history. Node/state IDs are used only when the URL dataset version
  matches current metadata; stale-version anchors reset to the current root.
- Support-one edges remain navigable. A source link is supplementary and never
  blocks traversal into a later shared position.
- Clearing a player filter aborts stale work and atomically resets filter,
  selection, path, node, state, board, URL, and neighborhood to the root.

## Failure scenarios covered

| Scenario | Required behavior |
| --- | --- |
| Two move orders reach one placement/state | One node/state with unioned, distinct-game continuations |
| Same placement has different side/castling/en-passant | One node, separate state occurrences and legal outgoing edges |
| A game revisits a node/state/edge | Support counts that game once; client history may contain the ID repeatedly |
| Two edges reach the same child | Preserve both edge IDs; never key by child ID |
| A unique line later transposes into shared play | Retain the whole bridge through the last shared placement |
| A unique tail never returns to shared play | Keep one source edge after the last shared placement, but do not invent a terminal |
| One game revisits a placement repeatedly | Count it once during shared-position discovery |
| Inputs differ between reconstruction passes | Abort before writing a valid manifest |
| Ending state also has outgoing edges | Report the ending count and continuations independently |
| Filter matches the node but not an edge | Keep structure cached; return edge support zero and hide it in the UI |
| Popular-player filter on the full corpus | Intersect from the cheaper side; never scan every selected game for every small posting |
| Filter is cleared after moves | Reset to root before issuing the unfiltered request |
| Filter/search/navigation response arrives late | Abort or discard it by generation |
| State ID does not belong to node ID | Reject the request |
| URL node/state IDs belong to an older dataset | Ignore them and load the current graph root |
| Graph contains a cycle | Visit each state once per neighborhood; keep traversal edges without recursive ancestry |
| Immediate move list exceeds state/byte budget | Reject atomically rather than return a partial move list |
| Deeper expansion exceeds a budget | Trim whole parent expansions and mark state frontiers |
| Identity hash or replay determinism fails | Abort the build through staging-table triggers |
| Source TCN moves from an empty/invalid square | Exclude it identically in both passes and report `position_replay_error` |
| Duplicate source UUID | Abort instead of inflating support |
| Interrupted full build | Leave the unpublished output/scratch isolated; never alter source or active artifact |
| Edge source link crosses the Next.js proxy | Allowlist only `/api/edges/{id}/games`; retain old node route for rollback |

## Reconstruction evidence

Input is the checked, immutable monthly snapshot:

- path: `snapshots/monthly-20260901/crawler-through-2026-08.db`
- bytes: `15,695,740,928`
- SHA-256: `262b4cfc356a81b8dde88d4f6db863f155f8e8c5df1f14284fc8acb043828228`
- SQLite quick check: `ok`
- foreign-key violations: `0`
- games: `8,487,878`
- crawl closure: ready, with no active, failed, or remaining jobs

The first, full-tail 1/823 rehearsal accepted 8,187 games and produced:

- 337,191 placement nodes;
- 338,383 state variants;
- 342,104 edges;
- 1,245,919 membership ordinals;
- a 68,458,206-byte final artifact;
- a 230,404,096-byte staging database;
- 486,948,864-byte peak RSS; and
- 366 accepted games/second during the measured build.

The rehearsal artifact passed component SHA-256 checks and structural
validation. Its root neighborhood returned 423 nodes, 453 states, and 461
edges in about 23 ms with a 260,724-byte encoded response.

A full-tail build was then stopped after 80,000 accepted games. Its random
SQLite B-tree staging writes were already slowing, its structural tables and
indexes dominated disk use, and the sample projected a roughly 70–75 GB final
artifact. The unpublished partial output and scratch were retained under
`failed-full-position-graph-sqlite-staging-20260901-80k`; neither source data nor
the active published artifact was touched.

The first production discovery attempt also exposed a source-level replay
error after 1.68 million accepted candidates: a recorded move attempted to move
from an empty `f2` square. That incomplete discovery was preserved separately,
and the versioned replay-exclusion policy above was added before restarting.

The two-pass policy was introduced in response. Its 1/823 rehearsal accepted
the same 8,187 games and produced:

- 20,327 placement nodes;
- 21,193 state variants;
- 24,408 edges;
- 286,053 membership ordinals;
- a 7,826,678-byte final artifact after adding the replay-policy declaration;
- 22,663,240 bytes of retained completion scratch;
- 171,409,408-byte peak RSS; and
- 413 accepted games/second across discovery and graph construction.

A larger 1/83 rehearsal accepted 81,394 games and produced:

- 188,164 placement nodes;
- 195,579 state variants;
- 221,366 edges;
- 3,371,171 membership ordinals;
- a 75,514,211-byte final artifact;
- 237,117,432 bytes of total scratch;
- 432,308,224-byte peak RSS; and
- 482 accepted games/second across both passes.

Both corrected rehearsals passed manifest checksums and full structural
validation. The larger run projects a roughly 6–7 GB final graph and 20–25 GB
of scratch for the checked corpus, subject to the greater shared-position
density of the complete dataset.

The replay-policy 1/823 artifact also passed a fresh-process reader and query
probe. Its hashed/structurally validated startup took about 40 ms, its unfiltered
root neighborhood returned 433 placement nodes, 473 states, and 481 edges in
about 27 ms and 258,609 encoded bytes, filtered roots stayed below the 256 KiB
cap, repeated responses were byte-deterministic after timing normalization, and
a support-one edge returned exactly one edge-scoped source game. The graph's
root IDs were node `12795` and state `9690`, confirming that the browser must
use manifest roots rather than assume ID zero.

The full build completed from the checked snapshot with:

- build/dataset ID `68a97678c3df093d243473e0844b373d669ac335`;
- 6,747,980 accepted games;
- 1,101,106 `empty_tcn`, 638,771 `short_non_checkmate`, and 21
  `position_replay_error` exclusions, accounting for all 8,487,878 source rows;
- 5,985,342 globally shared placements;
- 15,345,216 placement nodes;
- 15,951,206 rules-state occurrences;
- 17,672,975 directed edges;
- 361,216,254 membership ordinals;
- a 6,447,934,175-byte final artifact;
- 22,410,765,528 bytes of retained completion scratch;
- 2,500,132,864-byte peak RSS; and
- 21,092.64 seconds at 319.92 accepted games/second for discovery and graph
  construction.

The artifact is
`artifacts/opening/full-position-graph-through-202608-v1`, with result evidence
in `artifacts/opening/full-position-graph-through-202608-v1-result.json`.
Component SHA-256 checks and the full structural scan passed in 21.69 seconds.
The nonzero root IDs are node `9651009` and state `7275645`.

The command used was:

```bash
.venv/bin/python scripts/build_opening_position_graph.py \
  snapshots/monthly-20260901/crawler-through-2026-08.db \
  artifacts/opening/full-position-graph-through-202608-v1 \
  --temporary-directory artifacts/opening-build-temp/full-position-graph-through-202608-v1 \
  --snapshot-sha256 262b4cfc356a81b8dde88d4f6db863f155f8e8c5df1f14284fc8acb043828228 \
  --sample-modulus 1 \
  --result artifacts/opening/full-position-graph-through-202608-v1-result.json
```

The build read the checked snapshot with `mode=ro&immutable=1`. It did not
read or mutate `data/crawler.db`, and it does not replace either retained
`full-post-qualification-20260802-v2-*` rollback artifact.

The 20-repeat fresh-process benchmark is retained at
`artifacts/opening/full-position-graph-through-202608-v1-benchmark.json`.
Validated startup took 22.17 seconds: 2.53 seconds for component checksums,
19.53 seconds for the 48.97 million-record structural scan, 105 ms for the
254,180-entry player directory, and 5.9 ms to create the memory maps. The
unfiltered root returned 402 nodes, 402 states, and 405 edges in 241,764 bytes,
with 23.63 ms median and 26.52 ms p95 latency. The most frequent White filter
returned 438 nodes, 438 states, and 441 edges in 249,210 bytes, with 2.592 s
median and 2.677 s p95 latency. The most frequent Black filter returned the
same structural counts in 250,432 bytes, with 2.669 s median and 2.721 s p95
latency. Every repeated response was byte-deterministic after timing
normalization, an eight-ply mainline traversal succeeded, and a support-one
edge returned exactly one edge-scoped source game.

The first full benchmark attempt exposed a scale-only filtered-intersection
failure: it scanned all 62,000-plus selected games through a binary search for
every returned posting. The reader now chooses between probing the selected
games and scanning the posting once against a hashed selection based on the
estimated operation count. The same full query then completed in roughly 2.6
seconds instead of failing to complete after several minutes. This latency is
acceptable for validation but remains an explicit hosting/product tradeoff.

## Release gates after reconstruction

1. Full manifest checksum and structural validation must complete.
2. Root, filtered-player, transposition, cycle, ending, and edge-source queries
   must be compared with the semantic oracle/rehearsal.
3. Startup and query behavior must be measured against the full artifact.
4. Hosting feasibility must be decided from the measured full artifact; the
   rehearsal projection is not assumed to fit the current Vercel transport or
   runtime envelope.
5. Only then may a new immutable pointer, preview, or production publication be
   proposed. The old artifact remains the rollback version throughout.

The graph-specific local probe for gates 2–3 is:

```bash
.venv/bin/python scripts/benchmark_opening_position_graph.py \
  artifacts/opening/full-position-graph-through-202608-v1 \
  --repeats 20 \
  --result artifacts/opening/full-position-graph-through-202608-v1-benchmark.json
```

The older `benchmark_opening_service.py` remains a rollback-artifact benchmark;
it assumes intrinsic trie parents and node-scoped examples and must not be used
to certify a position graph.
