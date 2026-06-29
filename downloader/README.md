# Bughouse Downloader

Download a chess.com player's **bughouse** games into a local SQLite database. This is the
data-collection half of a larger goal — a Bughouse Opening Explorer that browses openings with
win-rate / frequency stats. This tool builds the game database that explorer will read.

## Why it exists

chess.com supports bughouse (`rules == "bughouse"`) and exposes every player's games through its
read-only [Published-Data API](https://www.chess.com/announcements/view/published-data-api) — no
auth required. This CLI walks a player's monthly archives, keeps the bughouse games, decodes their
moves, and stores them in SQLite with a progress bar and smart stop/resume.

## Install

```bash
cd downloader
python3 -m venv .venv && source .venv/bin/activate
pip install -e .            # add -e ".[dev]" to run the tests
```

## Usage

```bash
bughouse-dl USERNAME [--db games.db] [--from YYYY/MM] [--to YYYY/MM] [--force-refresh]
```

Examples:

```bash
bughouse-dl nochewycandy                       # all of this player's bughouse games
bughouse-dl nochewycandy --from 2025/01        # only 2025 onward
bughouse-dl larso --db games.db                # add another player into the same DB
```

## Stop & resume

Resume is **month-granular**. The `archives` table records which months are fully downloaded.
- Past months are immutable on chess.com, so a completed month is never re-fetched.
- The current (latest) month is always re-fetched, since it can still change.
- Each month is written in a single transaction, so pressing **Ctrl-C** mid-run leaves the database
  consistent — completed months are saved and the next run continues from there.

Use `--force-refresh` to ignore the ledger and re-fetch everything.

## What's stored

A `games` table, one row per board record keyed by chess.com's `uuid`:

| column | notes |
| --- | --- |
| `uuid` | primary key; dedups shared games across multiple downloaded users |
| `white_*` / `black_*` | username, rating, result per side |
| `time_control`, `time_class`, `rated`, `end_time`, `eco` | game metadata |
| `fen` | final position |
| `tcn` | raw chess.com move encoding, kept verbatim |
| `moves_json` | decoded moves: `{"from"/"drop", "to", "promotion"?}` per ply |
| `url` | link to the game on chess.com |

Raw `tcn` is preserved alongside the decoded `moves_json`, so nothing is lost if move decoding is
ever revised.

## Known limitations

- **No partner-board link.** Bughouse is two boards, but the API returns each board as a separate
  record with no field tying the pair together. Reconstructing pairs (by timestamp + shared players)
  is left to the explorer project.
- Bughouse records carry no PGN; moves come only from the `tcn` field, which this tool decodes.

## Tests

```bash
pytest
```
