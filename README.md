# Bughouse Opening Explorer

A tool for studying bughouse openings: download a player's games from chess.com,
index them into a position graph, and browse openings in a
**single-board**. You drill into positions and, for each continuation, see how
many games played it and the win split.

One self-contained Python package (`bughouse_explorer`) does everything — **download**, **index**,
and **serve** — writing to **one SQLite database**.

## The pipeline

```
chess.com  ──(download)──►  raw games ─┐
                                       ├─ data/games.db ──(query server)──► browser GUI
                     (index)──► graph ─┘
```

1. **download** walks a player's monthly archives on chess.com's public Published-Data API, keeps
   the bughouse games, and upserts them into the `games` table — storing chess.com's compact `tcn`
   move encoding verbatim (it is decoded later, at index time). It is resumable (a per-month
   ledger) and dedups across players by game `uuid`.
2. **index** replays each game's moves on a single-board engine, keying positions by FEN so
   transpositions merge, and writes a per-game **facts** graph (`positions`/`moves`/`game_facts`/
   `games_meta`) into the same file. Nothing is pre-aggregated — every statistic is computed at
   query time. Indexing is **incremental**: only games not yet in the index are processed, so
   updates stay fast even as the collection grows past a million games.
3. The **query server** (FastAPI) answers a read-only JSON API (`/api/moves`, `/api/games`,
   `/api/meta`, `/api/usernames`). 
4. The **frontend** (Vite + TypeScript + chessground) calls that API and navigates positions by id.

## Data model

One `data/games.db` holds two layers. The **raw store** is the irreplaceable download; the
**derived index** is regenerated from it (`index --rebuild`) and is what the server queries.

**Raw store** (written by `download`):

- **`games`** — one row per board, keyed by chess.com's `uuid`, so re-downloading or overlapping
  players dedup for free. Holds only the fields the index consumes (players, ratings, results,
  `url`, `time_control`, `end_time`) plus chess.com's compact `tcn` move encoding, decoded on the
  fly at index time. No secondary indexes — it's only ever read by its `uuid` PK / rowid.
- **`archives`** — the resume ledger, one row per `(username, year, month)`; `complete` months are
  never re-fetched.

**Derived index** (built by `index`, nothing pre-aggregated):

- **`positions(id, fen, fen_hash)`** — every distinct position, keyed by a FEN without move
  counters so transpositions merge. Across incremental runs a position is resolved by an indexed
  8-byte `fen_hash` (verified against the FEN text on a hit), far smaller than indexing the
  ~70-byte FEN itself.
- **`moves(parent_id, move_id → child_id, san, from_sq, to_sq, drop_piece)`** — one edge per
  distinct move out of a position: its SAN, origin/destination (or dropped piece), and the
  resulting child position.
- **`game_facts(parent_id, move_id, game_id, outcome, rating_sum)`** — the heart of the index, one
  row per (game, position) the game reached, recording which move it played there. `outcome` and
  `rating_sum` are denormalized so the common unfiltered query aggregates win/draw/loss and applies
  the rating filter with no join. References a dense integer `game_id`, not the 36-byte `uuid`.
- **`games_meta(game_id, uuid, white/black username + rating, outcome, url, time_control,
  end_time)`** — a compact per-game row the server returns in the games panel and joins to only
  when filtering by username.

`meta(key, value)` is shared: the raw layer stores `schema_version`; the index stores `max_ply`
and `root_id` (the start position's id).

## Quickstart

```bash
git clone https://github.com/Oh-My-Lands/bughouse-opening-explorer.git
cd bughouse-opening-explorer
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Then run the three steps (all against one `--db`, default `data/games.db`):

```bash
# 1. download a player's bughouse games (repeat for more players; resumable)
bughouse-explorer download SomeUsername
#    options: --from YYYY/MM  --to YYYY/MM  --force-refresh  --db PATH

# 2. build / update the opening index (incremental — only new games are processed)
bughouse-explorer index

# 3. serve the explorer (web UI + JSON API on http://localhost:8000)
bughouse-explorer serve
```

`bughouse-explorer update SomeUsername` does steps 1–2 in at once.

## Indexing depth and rebuilds

`--max-ply N` (default **40**) bounds how deep the index records each game. It is fixed once the
index exists; to change it, rebuild the whole index from the raw games (the raw games are kept, so
this needs no re-download):

```bash
bughouse-explorer index --max-ply 30 --rebuild
```

Everything else (rating, min-games, username) is a live query parameter — you never rebuild to
change a filter.

## Filters (live, no rebuild)

- **Mean rating ≥** — a slider; only games whose two players average at or above the threshold count.
- **Min games** — a slider (1–10, default 5); continuations played in fewer games are hidden.
- **White / Black username** — typeahead comboboxes; filter to a seat, or both for an exact pairing.
  Clicking a player's name in the games panel commits it to that seat's filter.

## Run the GUI

Two local processes during development: the query server and the Vite dev server.

```bash
# 1. query server (with the venv active)
bughouse-explorer serve            # serves http://localhost:8000

# 2. frontend dev server (in another shell)
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api -> :8000
```

Open http://localhost:5173. The board starts at the initial position; click a continuation row (or
drag a piece for normal moves) to drill in. Drops are played by clicking their row (no pocket to
drag from). Back / forward / arrow keys navigate; the move list and games panel update with the
position.

For a **single-process** run, `npm run build` then `bughouse-explorer serve` — it mounts the built
`frontend/dist` alongside the API on one port (http://localhost:8000). (`bughouse-explorer-serve`
is kept as an alias for `bughouse-explorer serve`.)

## Layout

```
bughouse-opening-explorer/
  bughouse_explorer/
    api.py        # chess.com Published-Data API client
    tcn.py        # decode chess.com's tcn move encoding (drops, promotions)
    download.py   # walk a player's archives, keep bughouse games, upsert into the raw store
    engine.py     # single-board move applier -> FEN + SAN (handles drops, castling, ep, promotion)
    indexer.py    # incremental position-graph index built from the raw games (same db file)
    db.py         # unified schema + write helpers (raw store + index)
    server.py     # FastAPI query server
    cli.py        # bughouse-explorer download / index / serve / update
  frontend/
    src/{main,db,explorer,combobox}.ts · src/styles.css · index.html
  tests/          # test_engine.py · test_tcn.py · test_indexer.py
  data/           # generated database lives here (gitignored)
```

## Tests

```bash
pytest
```

The tests replay real games' full move lists (asserting the engine reproduces the exact final
position chess.com recorded), decode the `tcn` format, and check incremental indexing.

## Bughouse constraints

chess.com bughouse records carry no PGN (moves come only from the decoded `tcn` field), and the API
returns each of the two boards as a separate record with no field linking the pair. This project
works within those constraints: the raw `tcn` is the only move record kept (decoded on demand when
indexing), and the explorer treats each board as a standalone single-board game.

## Possible future features

More filters (time-class / date / color), reconstructing the two boards of a game, engine eval.

## License

[AGPL-3.0](LICENSE).
