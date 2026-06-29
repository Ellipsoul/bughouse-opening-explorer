# Bughouse Opening Toolkit

A two-part toolkit for studying **chess.com bughouse** openings: download a player's games, index
them into a position graph, and browse openings — with frequency and win-rate stats — in a
**single-board** explorer (like the lichess crazyhouse explorer, but with no pocket; dropped pieces
just appear on their square).

## The pipeline

```
chess.com API ──[ downloader ]──► games.db ──[ explorer indexer ]──► explorer.db ──[ query server ]──► browser GUI
```

1. **[`downloader/`](downloader/)** — a CLI (`bughouse-dl`) that walks a player's monthly archives on
   chess.com's public Published-Data API, keeps the bughouse games, decodes their `tcn` move encoding,
   and stores them in a local SQLite **`games.db`**.
2. **[`explorer/`](explorer/)** — an indexer (`bughouse-explorer-index`) that replays each game on a
   single-board engine and builds **`explorer.db`** (a position graph), plus a FastAPI query server
   (`bughouse-explorer-serve`) and a Vite/TypeScript/chessground frontend that browses it.

The downloader and explorer are independent Python packages that share no code — the only thing passing between
them is the `games.db` file, which the indexer reads via `--games-db`.

## Quickstart

The two packages have disjoint dependencies, so install whichever half you need (or both):

```bash
git clone <this-repo> bughouse && cd bughouse
python3 -m venv .venv && source .venv/bin/activate

pip install -e downloader/      # the bughouse-dl scraper
pip install -e explorer/        # the indexer + query server
```

Then run the pipeline:

```bash
# 1. download a player's bughouse games into games.db
bughouse-dl SomeUsername --db games.db

# 2. build the opening index (run from explorer/)
cd explorer
bughouse-explorer-index --games-db ../downloader/games.db --out frontend/public/explorer.db

# 3. serve it
bughouse-explorer-serve --db frontend/public/explorer.db    # http://localhost:8000
```

See **[downloader/README.md](downloader/README.md)** and **[explorer/README.md](explorer/README.md)**
for the full details, options, and the dev workflow (Vite dev server + API proxy).

> **The databases are generated, not shipped.** `games.db` (~2 GB) and `explorer.db` (~4 GB) are built
> by running the pipeline above and are deliberately **not** committed to this repository — regenerate
> them locally.

## Bughouse contraints
chess.com bughouse records carry no PGN (moves come only from the decoded `tcn` field), and the API
returns each of the two boards as a separate record with no field linking the pair. This toolkit works
within those constraints: the downloader preserves the raw `tcn` alongside the decoded moves, and the
explorer treats each board as a standalone single-board game.

## License

[AGPL-3.0](LICENSE). 
