# Bughouse Opening Explorer

A **single-board** opening explorer for chess.com bughouse games — feature-wise like the lichess
crazyhouse explorer, but with **no pocket** (dropped pieces simply appear on their square). You drill
into positions and, for each continuation, see how many games played it and the win split.

It reads the `games.db` produced by the companion **bughouse-downloader** project (see the
[repo root README](../README.md) for the full pipeline).

## How it works

```
games.db  ──(Python indexer)──►  explorer.db  ──(FastAPI query server)──►  browser GUI
```

1. The **indexer** (Python) replays each game's moves on a single-board engine, keying positions by
   FEN so transpositions merge, and writes a per-game **facts** graph to `explorer.db`. Nothing is
   pre-aggregated — every statistic (frequency, win-rate, rating, username/side) is computed at query
   time, so filters are just `WHERE`/`HAVING` clauses over the facts.
2. A small local **query server** (FastAPI, `bughouse-explorer-serve`) reads `explorer.db` and answers
   a read-only JSON API (`/api/moves`, `/api/games`, `/api/meta`, `/api/usernames`). The database
   stays on disk and only small query results cross to the page, so the dataset can grow large without
   bloating the client.
3. The **frontend** (Vite + TypeScript + chessground) calls that API and navigates positions by their
   integer id.

### Filters
Because stats are aggregated on demand, the GUI offers live filters with no rebuild:
- **Mean rating ≥** — a slider; only games whose two players average at or above the threshold count.
- **Min games** — a slider (1–10, default 5); continuations played in fewer games than this are
  hidden. This is a query parameter, not a build-time prune — drag it to 1 to surface rare lines.
- **White / Black username** — typeahead comboboxes; filter to a seat, or both for an exact pairing.
  Clicking a player's name in the games panel commits it to that seat's filter.

## Build the index

Requires a `games.db` from the downloader. From this `explorer/` directory:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
bughouse-explorer-index --games-db /path/to/games.db --out frontend/public/explorer.db
```

The only build-time option is `--max-ply N` (plies recorded per game, default **40**) — it bounds how
deep the index goes. Everything else (rating, min-games, username) is a live query parameter, so you
never rebuild to change a filter.

## Run the GUI

Two local processes during development: the query server and the Vite dev server.

```bash
# 1. query server (from explorer/, with the venv active)
bughouse-explorer-serve --db frontend/public/explorer.db    # serves http://localhost:8000

# 2. frontend dev server (in another shell)
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api -> :8000
```

Open http://localhost:5173. The board starts at the initial position; click a continuation row (or
drag a piece for normal moves) to drill in. Drops are played by clicking their row (no pocket to drag
from). Back / forward / arrow keys navigate; the move list and games panel update with the position.

For a **single-process** run, `npm run build` then start `bughouse-explorer-serve` — it mounts the
built `frontend/dist` alongside the API on one port (http://localhost:8000). That is the only "server"
in the system; the Vite dev server above is a development convenience that proxies to it.

## Layout

```
explorer/
  bughouse_explorer/
    engine.py     # single-board move applier -> FEN + SAN (handles drops, castling, ep, promotion)
    indexer.py    # games.db -> explorer.db (CLI: bughouse-explorer-index)
    db.py         # explorer.db schema + write helpers
    server.py     # FastAPI query server (CLI: bughouse-explorer-serve)
  frontend/
    src/{main,db,explorer,combobox}.ts · src/styles.css · index.html
    public/explorer.db          # built by the indexer (not committed)
  tests/test_engine.py          # replays real games and checks the final position
```

## Tests

```bash
pytest
```

The headline test replays real games' full move lists and asserts the engine reproduces the exact
final position chess.com recorded.

## Out of scope (possible follow-ups)
- More filters (time-class / date / color), reconstructing the two boards of a game, engine eval.
