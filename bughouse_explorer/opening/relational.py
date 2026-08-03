"""Compact SQLite baseline with explicit per-node game membership."""

from collections import Counter
from bisect import bisect_left
import json
from pathlib import Path
import sqlite3

from .model import Branch, NodeView, PrefixNotFound, QueryFilter, replay_prefix
from .trie import prepare_trie


SCHEMA = """
CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE games(
    ordinal INTEGER PRIMARY KEY,
    uuid TEXT NOT NULL UNIQUE,
    white_username TEXT NOT NULL,
    black_username TEXT NOT NULL,
    white_rating INTEGER,
    black_rating INTEGER,
    white_result TEXT,
    black_result TEXT,
    end_time INTEGER,
    time_control TEXT,
    rated INTEGER NOT NULL,
    source TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    url TEXT,
    provenance_flags TEXT NOT NULL
);
CREATE INDEX idx_games_white ON games(white_username, ordinal);
CREATE INDEX idx_games_black ON games(black_username, ordinal);
CREATE INDEX idx_games_pair ON games(white_username, black_username, ordinal);
CREATE TABLE nodes(
    id INTEGER PRIMARY KEY,
    parent_id INTEGER,
    move_token TEXT,
    ply INTEGER NOT NULL,
    interval_start INTEGER NOT NULL,
    interval_end INTEGER NOT NULL,
    terminal_ordinal INTEGER
);
CREATE TABLE edges(
    parent_id INTEGER NOT NULL,
    move_token TEXT NOT NULL,
    child_id INTEGER NOT NULL,
    PRIMARY KEY(parent_id, move_token)
) WITHOUT ROWID;
CREATE TABLE membership(
    node_id INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY(node_id, ordinal)
) WITHOUT ROWID;
CREATE INDEX idx_membership_game ON membership(ordinal, node_id);
CREATE TABLE endings(
    node_id INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY(node_id, ordinal)
) WITHOUT ROWID;
CREATE TABLE node_results(
    node_id INTEGER NOT NULL,
    result TEXT NOT NULL,
    game_count INTEGER NOT NULL,
    PRIMARY KEY(node_id, result)
) WITHOUT ROWID;
"""


def build_relational_index(games, path, *, source_fingerprint: str):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    prepared = prepare_trie(games, source_fingerprint=source_fingerprint)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "PRAGMA page_size=4096; PRAGMA journal_mode=OFF; "
            "PRAGMA synchronous=OFF; PRAGMA temp_store=MEMORY; " + SCHEMA
        )
        connection.executemany(
            """
            INSERT INTO games(
                ordinal, uuid, white_username, black_username,
                white_rating, black_rating, white_result, black_result,
                end_time, time_control, rated, source, content_hash, url,
                provenance_flags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    ordinal,
                    game.uuid,
                    game.white_username,
                    game.black_username,
                    game.white_rating,
                    game.black_rating,
                    game.white_result,
                    game.black_result,
                    game.end_time,
                    game.time_control,
                    int(game.rated),
                    game.source,
                    game.content_hash,
                    game.url,
                    json.dumps(game.provenance_flags, separators=(",", ":")),
                )
                for ordinal, game in enumerate(prepared.games)
            ),
        )
        connection.executemany(
            "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    node.id,
                    node.parent_id,
                    node.move_token,
                    node.ply,
                    node.interval_start,
                    node.interval_end,
                    node.terminal_ordinal,
                )
                for node in prepared.nodes
            ),
        )
        connection.executemany(
            "INSERT INTO edges VALUES (?, ?, ?)",
            (
                (node.id, prepared.nodes[child].move_token, child)
                for node in prepared.nodes
                for child in node.children
            ),
        )
        connection.executemany(
            "INSERT INTO membership VALUES (?, ?)",
            (
                (node.id, ordinal)
                for node in prepared.nodes
                for ordinal in range(node.interval_start, node.interval_end)
            ),
        )
        connection.executemany(
            "INSERT INTO endings VALUES (?, ?)",
            (
                (node.id, ordinal)
                for node in prepared.nodes
                for ordinal in node.endings
            ),
        )
        connection.executemany(
            "INSERT INTO node_results VALUES (?, ?, ?)",
            (
                (node.id, result, count)
                for node in prepared.nodes
                for result, count in Counter(
                    prepared.games[ordinal].white_result or "unknown"
                    for ordinal in range(node.interval_start, node.interval_end)
                ).items()
            ),
        )
        metadata = {
            "adapter_policy": "opening-adapter-v1",
            "build_id": prepared.build_id,
            "games": len(prepared.games),
            "node_semantics": "exact-decoded-move-prefix-v1",
            "nodes": len(prepared.nodes),
            "source_fingerprint": source_fingerprint,
            "terminal_policy": "first-distinct-support-one-or-game-end-v1",
        }
        connection.executemany(
            "INSERT INTO metadata VALUES (?, ?)",
            ((key, json.dumps(value, sort_keys=True)) for key, value in metadata.items()),
        )
        connection.execute("ANALYZE")
    return prepared.build_id


class RelationalIndex:
    def __init__(self, path):
        resolved = Path(path).resolve()
        self.connection = sqlite3.connect(
            f"file:{resolved}?mode=ro&immutable=1", uri=True
        )
        self.connection.row_factory = sqlite3.Row

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def _node_id(self, prefix):
        node_id = 0
        for token in prefix:
            row = self.connection.execute(
                "SELECT child_id FROM edges WHERE parent_id=? AND move_token=?",
                (node_id, token),
            ).fetchone()
            if row is None:
                raise PrefixNotFound(prefix)
            node_id = row["child_id"]
        return node_id

    def _matching_games(self, node_id, query_filter):
        if query_filter.white_username and query_filter.black_username:
            index = "idx_games_pair"
            clauses = "g.white_username=? AND g.black_username=?"
            values = (
                query_filter.white_username,
                query_filter.black_username,
            )
        elif query_filter.white_username:
            index = "idx_games_white"
            clauses = "g.white_username=?"
            values = (query_filter.white_username,)
        else:
            index = "idx_games_black"
            clauses = "g.black_username=?"
            values = (query_filter.black_username,)
        rows = self.connection.execute(
            f"""
            SELECT g.ordinal, COALESCE(g.white_result, 'unknown') AS result
            FROM games AS g INDEXED BY {index}
            JOIN membership AS m ON m.ordinal=g.ordinal
            WHERE {clauses} AND m.node_id=?
            ORDER BY g.ordinal
            """,
            (*values, node_id),
        )
        return tuple((row["ordinal"], row["result"]) for row in rows)

    def query(self, prefix=(), query_filter: QueryFilter | None = None):
        prefix = tuple(prefix)
        node_id = self._node_id(prefix)
        node = self.connection.execute(
            "SELECT * FROM nodes WHERE id=?", (node_id,)
        ).fetchone()
        selected = None
        selected_results = None
        if query_filter and (
            query_filter.white_username or query_filter.black_username
        ):
            matches = self._matching_games(node_id, query_filter)
            selected = tuple(ordinal for ordinal, _result in matches)
            selected_results = dict(matches)
        support = (
            len(selected)
            if selected is not None
            else node["interval_end"] - node["interval_start"]
        )
        ended = self.connection.execute(
            """
            SELECT g.ordinal, g.uuid
            FROM endings AS e JOIN games AS g ON g.ordinal=e.ordinal
            WHERE e.node_id=? ORDER BY g.ordinal
            """,
            (node_id,),
        ).fetchall()
        branches = self.connection.execute(
            """
            SELECT e.move_token, e.child_id, n.interval_start, n.interval_end,
                   n.interval_end - n.interval_start AS support
            FROM edges AS e JOIN nodes AS n ON n.id=e.child_id
            WHERE e.parent_id=? ORDER BY e.move_token
            """,
            (node_id,),
        ).fetchall()
        sole_uuid = None
        if selected is not None and len(selected) == 1:
            sole_uuid = self.connection.execute(
                "SELECT uuid FROM games WHERE ordinal=?",
                (selected[0],),
            ).fetchone()["uuid"]
            branches = ()
        elif selected is None and node["terminal_ordinal"] is not None:
            sole_uuid = self.connection.execute(
                "SELECT uuid FROM games WHERE ordinal=?",
                (node["terminal_ordinal"],),
            ).fetchone()["uuid"]
        if selected is not None:
            selected_set = set(selected)
            ended = [row for row in ended if row["ordinal"] in selected_set]
            filtered_branches = []
            for row in branches:
                slice_start = bisect_left(selected, row["interval_start"])
                slice_end = bisect_left(selected, row["interval_end"])
                count = slice_end - slice_start
                if count:
                    results = Counter(
                        selected_results[ordinal]
                        for ordinal in selected[slice_start:slice_end]
                    )
                    filtered_branches.append(
                        Branch(row["move_token"], count, tuple(sorted(results.items())))
                    )
            branch_records = tuple(filtered_branches)
        else:
            branch_records = []
            for row in branches:
                results = self.connection.execute(
                    "SELECT result, game_count FROM node_results WHERE node_id=? ORDER BY result",
                    (row["child_id"],),
                )
                branch_records.append(
                    Branch(
                        row["move_token"],
                        row["support"],
                        tuple((result["result"], result["game_count"]) for result in results),
                    )
                )
            branch_records = tuple(branch_records)
        return NodeView(
            prefix=prefix,
            position_fen=replay_prefix(prefix),
            support=support,
            branches=branch_records,
            ended_game_uuids=tuple(row["uuid"] for row in ended),
            sole_game_uuid=sole_uuid,
        )
