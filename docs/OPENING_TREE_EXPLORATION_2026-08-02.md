# Opening-tree exploration — 2 August 2026

This document records read-only product exploration performed after recovery
hygiene completed. No crawler request, raw-database mutation, crawler-to-index
adapter, or production opening-tree change was made in this session.

## Outcome

The existing local explorer is a credible behavioral reference, but it cannot
yet consume `data/crawler.db`. Its legacy indexer expects a different `games`
table in `data/games.db`, records a fixed number of plies per game, and has no
explicit terminal-node reference for a position supported by one game.

The next implementation should keep the existing position graph and indexed
seat-filter ideas, introduce a crawler adapter, and replace fixed-depth-only
indexing with support-aware termination:

1. replay every policy-accepted non-empty game once to count distinct-game
   support for each canonical position;
2. replay the accepted games again to emit positions, edges, aggregates, and
   the membership required for filters;
3. stop a game's emitted path at the first position whose global support is
   one, store an explicit reference to that sole game, and also stop at the
   actual end of a game; and
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

## Terminal-node semantics

For the first implementation, define a position as unique when its canonical
position key occurs in exactly one distinct accepted board. Count a board no
more than once at a position even if repetition revisits that position.
Transpositions across different move orders therefore merge correctly.

Global support cannot be known when the first game is streamed. A deterministic
exact build needs two passes (or an equivalent build-then-compaction design).
A two-pass build avoids writing deep per-game facts that will be discarded:

- pass one computes support per canonical position from all accepted games;
- pass two emits each game's path only through its first globally unique
  position and writes a terminal reference there.

A global unique position remains unique under every filter, so it is always a
safe physical stopping point. A filtered view can become unique earlier. For
example, a position may have many games globally but only one with a selected
player as Black. The API should calculate filtered continuation/support counts
from indexed game membership and return that one game as the filtered terminal
instead of forcing the user down the deeper global path.

The terminal payload should contain a stable board UUID or internal game id and
the display fields needed for a bounded game link. A concrete schema should be
chosen only after the representative benchmark, but the first design must make
terminal membership explicit rather than inferring it from an outgoing edge.

Games that never reach global support one stop at their real final position.
The build should still retain a defensive replay limit and count/report any
decode error or safety truncation; it must not silently convert a safety cap
into an ordinary unique terminal.

## Exploratory uniqueness measurements

Two deterministic, full-rowid-range samples were replayed from an immutable
read-only connection to `data/crawler.db`. These were in-memory analyses, not
derived-index builds, and they made no database changes.

| Sample | Games | Full plies | Mean first-unique ply | P50 | P90 | P95 | Adaptive retained plies | Retained share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| about 10k | 9,978 | 457,022 | 10.19 | 10 | 15 | 17 | not retained as a durable build | 20.7% |
| about 50k | 49,872 | 2,274,749 | 11.87 | 12 | 17 | 18 | 545,418 | 24.0% |

In the 49,872-game sample, 45,040 games reached a globally unique position and
4,832 did not. The maximum first-unique ply was 29. Median position support at
sampled depth fell from 3,618 games at ply 2, to 105 at ply 6, to 4 at ply 10,
and to 1 at ply 12.

These figures support the adaptive design but are not a full-corpus forecast.
Uniqueness moved later as sample size increased, so the full 7,132,391-game
move-bearing corpus will have deeper shared lines. A representative on-disk
build must measure actual size, write amplification, query latency, and depth
distribution before the production schema or capacity forecast is frozen.

The raw corpus contains 325,470,732 valid plies across those 7,132,391 boards.
Replaying the moves is tractable on this hardware; the likely dominant risk is
the size and write pattern of per-game membership needed for arbitrary filters.
That remains a hypothesis until the representative SQLite build is measured.

## Decisions for the implementation slice

The next session should make and document these decisions before a large build:

1. Inclusion policy and provenance: start from non-empty, successfully decoded
   TCN; explicitly decide whether the 561 callback-only boards are included;
   count empty TCN and every other exclusion by reason; never delete raw rows.
2. Position identity: retain the canonical four-field position key, full-key
   verification after hash lookup, transposition merging, and per-game
   de-duplication on repeated positions.
3. Terminal contract: define global and filtered support-one responses,
   end-of-game terminals, game references, and safety-truncation disclosure.
4. Filter shape: make White and Black separate indexed dimensions and benchmark
   exact player-plus-colour branch/support queries at root and deep positions.
5. Build shape: compare two-pass support-first construction with any proposed
   alternative using a checked raw snapshot, never the live crawler database.
6. Benchmark ladder: begin with a deterministic representative subset, record
   accepted/skipped counts, plies/s, first-unique distribution, tables/indexes,
   WAL/temp/RAM/final bytes, and cold/warm filtered and unfiltered latency.
7. Publication boundary: version policy, source watermark, and derived schema;
   validate before publishing; keep the browser on bounded branch responses.

## Copy-ready prompt for the fresh session

```text
Continue work in:
/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer

Read, in order:
1. docs/README.md
2. docs/HANDOFF_2026-08-01.md
3. docs/OPENING_TREE_EXPLORATION_2026-08-02.md
4. docs/PLATFORM_ARCHITECTURE.md
5. docs/BACKUP_RECOVERY.md

Execute the first opening-tree product slice. Preserve data/crawler.db as the
lossless raw source and do not make Chess.com requests or begin a crawl. Work
against a checked snapshot or disposable derived database.

First freeze the derived-index inclusion/provenance policy and exact terminal
semantics. A terminal is reached at the first canonical position supported by
one distinct accepted game, or at game end. Repeated visits by one game count
once. Global construction needs exact support over all accepted games; filtered
views may terminate earlier when one player's games for the selected White or
Black seat have support one.

Then implement the crawler-to-index adapter and a deterministic representative
SQLite build using TDD. Preserve explicit game references at terminals and
efficient independent White/Black player filtering. Measure accepted/skipped
games and reasons, plies and games per second, unique-depth distribution,
positions/edges/membership/aggregates, peak RAM, temp/WAL/final bytes, and cold
and warm root/deep queries with and without player-plus-colour filters.

Do not build the full corpus until the representative benchmark is validated
and its capacity implications are documented. Do not integrate the production
Next.js UI in the same slice unless the adapter and benchmark gates are already
complete. Preserve unrelated changes; do not commit or push unless requested.
```
