#!/usr/bin/env python3
"""Read-only snapshot comparison for planning incremental opening builds.

The output contains aggregate counts and small adapter-compatible diagnostic
subsets, not a serving artifact. All source databases are opened immutable.
"""

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from bughouse_explorer.opening.adapter import (
    ADAPTER_POLICY_VERSION,
    CrawlerSnapshotAdapter,
)
from bughouse_explorer.opening.position_graph import result_bucket


GAME_FIELDS = (
    "tcn", "rules", "initial_setup", "source", "end_time", "time_control",
    "rated", "url", "content_hash",
)
SUBSET_SCHEMA = """
CREATE TABLE players(id INTEGER PRIMARY KEY, username TEXT);
CREATE TABLE games(uuid TEXT PRIMARY KEY, tcn TEXT, rules TEXT,
 initial_setup TEXT, source TEXT, end_time INTEGER, time_control TEXT,
 rated INTEGER, url TEXT, content_hash TEXT);
CREATE TABLE game_participants(game_uuid TEXT, color TEXT, player_id INTEGER,
 rating INTEGER, result TEXT, PRIMARY KEY(game_uuid, color));
"""


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def month(timestamp):
    if timestamp is None:
        return "unknown"
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m")


def analyze(
    before, after, output, *, expected_before=None, expected_after=None, progress=print
):
    before, after, output = (Path(path).resolve() for path in (before, after, output))
    for source in (before, after):
        if source.name == "crawler.db" and source.parent.name == "data":
            raise ValueError("use checked snapshots, never data/crawler.db")
        if not source.is_file():
            raise FileNotFoundError(source)
    if before == after:
        raise ValueError("comparison requires different source paths")
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    started = time.perf_counter()
    timings = {}
    hashes = {}
    for name, source, expected in (
        ("before", before, expected_before),
        ("after", after, expected_after),
    ):
        progress(f"hashing {name} snapshot", flush=True)
        hashes[name] = sha256(source)
        if expected and hashes[name] != expected.casefold():
            raise ValueError(f"{name} snapshot checksum mismatch")
    timings["hash_seconds"] = time.perf_counter() - started
    connection = sqlite3.connect(":memory:", uri=True)
    connection.execute(
        "ATTACH DATABASE ? AS old", (f"{before.as_uri()}?mode=ro&immutable=1",)
    )
    connection.execute(
        "ATTACH DATABASE ? AS new", (f"{after.as_uri()}?mode=ro&immutable=1",)
    )
    connection.execute("CREATE TEMP TABLE candidates(uuid TEXT PRIMARY KEY) WITHOUT ROWID")
    connection.execute("CREATE TEMP TABLE renamed(id INTEGER PRIMARY KEY)")
    progress("comparing game rows", flush=True)
    phase = time.perf_counter()
    counts = {
        label: connection.execute(f"SELECT COUNT(*) FROM {schema}.games").fetchone()[0]
        for label, schema in (("before_boards", "old"), ("after_boards", "new"))
    }
    flags = Counter({f"existing_{field}_changed": 0 for field in GAME_FIELDS})
    flags["existing_rowid_changed"] = 0
    new_uuids = set()
    deleted_uuids = set()
    new_months = Counter()
    predicate = " OR ".join(f"n.{field} IS NOT o.{field}" for field in GAME_FIELDS)
    columns = ", ".join(f"n.{field} IS NOT o.{field}" for field in GAME_FIELDS)
    for row in connection.execute(f"""
        SELECT n.uuid, o.uuid, n.end_time, n.rowid IS NOT o.rowid, {columns}
        FROM new.games n LEFT JOIN old.games o ON o.uuid=n.uuid
        WHERE o.uuid IS NULL OR n.rowid IS NOT o.rowid OR {predicate}
    """):
        uuid, old_uuid, end_time, reordered, *changes = row
        connection.execute("INSERT OR IGNORE INTO candidates VALUES (?)", (uuid,))
        if old_uuid is None:
            new_uuids.add(uuid)
            new_months[month(end_time)] += 1
        else:
            flags["existing_rowid_changed"] += reordered
            for field, changed in zip(GAME_FIELDS, changes):
                flags[f"existing_{field}_changed"] += changed
    for (uuid,) in connection.execute("""
        SELECT o.uuid FROM old.games o LEFT JOIN new.games n ON n.uuid=o.uuid
        WHERE n.uuid IS NULL
    """):
        deleted_uuids.add(uuid)
        connection.execute("INSERT OR IGNORE INTO candidates VALUES (?)", (uuid,))
    timings["game_diff_seconds"] = time.perf_counter() - phase
    progress("comparing participant rows and usernames", flush=True)
    phase = time.perf_counter()
    connection.execute("""
        INSERT INTO renamed SELECT n.id FROM new.players n JOIN old.players o ON o.id=n.id
        WHERE n.username IS NOT o.username
    """)
    participant_candidates = set()
    for (uuid,) in connection.execute("""
        SELECT n.game_uuid FROM new.game_participants n
        LEFT JOIN old.game_participants o ON o.game_uuid=n.game_uuid AND o.color=n.color
        WHERE o.game_uuid IS NULL OR n.player_id IS NOT o.player_id
           OR n.rating IS NOT o.rating OR n.result IS NOT o.result
           OR n.player_id IN (SELECT id FROM renamed)
        UNION
        SELECT o.game_uuid FROM old.game_participants o
        LEFT JOIN new.game_participants n ON n.game_uuid=o.game_uuid AND n.color=o.color
        WHERE n.game_uuid IS NULL
    """):
        participant_candidates.add(uuid)
        connection.execute("INSERT OR IGNORE INTO candidates VALUES (?)", (uuid,))
    counts["existing_participant_candidate_boards"] = len(
        participant_candidates - new_uuids - deleted_uuids
    )
    timings["participant_diff_seconds"] = time.perf_counter() - phase
    progress("classifying adapter outcomes from diagnostic subsets", flush=True)
    phase = time.perf_counter()
    subsets = {}
    for name, schema in (("before", "old"), ("after", "new")):
        path = output / f"{name}-candidate-subset.db"
        with sqlite3.connect(path) as subset:
            subset.executescript(SUBSET_SCHEMA)
            subset.executemany(
                "INSERT INTO players VALUES (?, ?)",
                connection.execute(f"SELECT id, username FROM {schema}.players"),
            )
            game_rows = connection.execute(f"""
                SELECT g.rowid, g.uuid, {', '.join('g.' + field for field in GAME_FIELDS)}
                FROM candidates c CROSS JOIN {schema}.games g ON g.uuid=c.uuid
                ORDER BY g.rowid
            """)
            columns = ", ".join(("rowid", "uuid", *GAME_FIELDS))
            placeholders = ",".join("?" for _ in range(2 + len(GAME_FIELDS)))
            subset.executemany(
                f"INSERT INTO games({columns}) VALUES ({placeholders})", game_rows
            )
            subset.executemany(
                "INSERT INTO game_participants VALUES (?, ?, ?, ?, ?)",
                connection.execute(f"""
                    SELECT p.game_uuid, p.color, p.player_id, p.rating, p.result
                    FROM candidates c CROSS JOIN {schema}.game_participants p
                    ON p.game_uuid=c.uuid
                """),
            )
        subsets[name] = path
    # Adapter skips lack UUIDs: recover identity by the preserved source rowid.
    def outcomes(path):
        with sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True) as subset:
            identities = dict(subset.execute("SELECT rowid, uuid FROM games"))
        return {
            identities[item.source_rowid]: item
            for item in CrawlerSnapshotAdapter(path).iter_outcomes()
        }
    old_outcomes, new_outcomes = outcomes(subsets["before"]), outcomes(subsets["after"])
    classifications = Counter()
    metadata_fields = Counter()
    result_buckets = Counter()
    renamed_pairs = set()
    added_skips = Counter()
    accepted_months = Counter()
    for uuid in new_uuids:
        outcome = new_outcomes[uuid]
        if outcome.game:
            classifications["added_adapter_accepted"] += 1
            accepted_months[month(outcome.game.end_time)] += 1
        else:
            added_skips[outcome.skip_reason] += 1
    for uuid in deleted_uuids:
        status = "accepted" if old_outcomes[uuid].game else "skipped"
        classifications[f"deleted_adapter_{status}"] += 1
    for uuid in old_outcomes.keys() & new_outcomes.keys():
        old, new = old_outcomes[uuid], new_outcomes[uuid]
        if old.game is None or new.game is None:
            old_status = "accepted" if old.game else old.skip_reason
            new_status = "accepted" if new.game else new.skip_reason
            classifications[f"existing_{old_status}_to_{new_status}"] += 1
        else:
            old_payload, new_payload = asdict(old.game), asdict(new.game)
            for field, value in old_payload.items():
                if value != new_payload[field]:
                    metadata_fields[field] += 1
                    if field in {"white_username", "black_username"}:
                        renamed_pairs.add((value, new_payload[field]))
            if result_bucket(old.game) != result_bucket(new.game):
                transition = f"{result_bucket(old.game)} -> {result_bucket(new.game)}"
                result_buckets[transition] += 1
            if old.game.move_tokens != new.game.move_tokens:
                classifications["existing_accepted_moves_changed"] += 1
            elif old_payload != new_payload:
                old_semantics = {
                    k: v for k, v in old_payload.items() if k != "content_hash"
                }
                new_semantics = {
                    k: v for k, v in new_payload.items() if k != "content_hash"
                }
                if old_semantics == new_semantics:
                    classifications["existing_accepted_content_hash_only"] += 1
                else:
                    classifications["existing_accepted_metadata_changed"] += 1
            else:
                classifications["existing_adapter_unchanged"] += 1
    counts.update(
        new_boards=len(new_uuids),
        deleted_boards=len(deleted_uuids),
        candidate_boards=connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0],
    )
    counts["existing_candidate_boards"] = (
        counts["candidate_boards"] - len(new_uuids) - len(deleted_uuids)
    )
    counts["unchanged_boards"] = (
        counts["before_boards"] - len(deleted_uuids) - counts["existing_candidate_boards"]
    )
    timings["subset_and_classification_seconds"] = time.perf_counter() - phase
    timings["total_seconds"] = time.perf_counter() - started
    report = dict(
        adapter_policy=ADAPTER_POLICY_VERSION,
        before=str(before),
        after=str(after),
        snapshot_sha256=hashes,
        counts=counts,
        game_field_changes=dict(sorted(flags.items())),
        classifications=dict(sorted(classifications.items())),
        new_board_months=dict(sorted(new_months.items())),
        new_adapter_accepted_months=dict(sorted(accepted_months.items())),
        new_adapter_skips=dict(sorted(added_skips.items())),
        timings=timings,
        existing_accepted_field_changes=dict(sorted(metadata_fields.items())),
        existing_result_bucket_changes=dict(sorted(result_buckets.items())),
        distinct_username_replacement_pairs=len(renamed_pairs),
        diagnostic_subsets={name: str(path) for name, path in subsets.items()},
        scope=(
            "adapter admission only; graph replay exclusions and shared-position "
            "impacts require separate analysis"
        ),
    )
    connection.close()
    with (output / "snapshot-delta.json").open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("output", type=Path, help="fresh diagnostic directory")
    parser.add_argument("--before-sha256", required=True)
    parser.add_argument("--after-sha256", required=True)
    args = parser.parse_args()
    report = analyze(
        args.before, args.after, args.output,
        expected_before=args.before_sha256, expected_after=args.after_sha256,
    )
    print(json.dumps(report["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
