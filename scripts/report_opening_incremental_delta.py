#!/usr/bin/env python3
"""Audit a completed temporal generation and enumerate every threshold owner.

Both generations stay immutable. This is verification work, timed separately
from the incremental update and export. JSONL witnesses avoid a large RAM set.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import time

from bughouse_explorer.opening.incremental import Generation, encoded, load_game
from bughouse_explorer.opening.position_graph_streaming import _replay_game


def report(generation, output):
    started = time.monotonic()
    generation = Generation(generation)
    complete = generation.verify_complete()
    with sqlite3.connect(
        f"{generation.path.as_uri()}?mode=ro&immutable=1", uri=True
    ) as c:
        parent_path = json.loads(
            c.execute("SELECT value FROM meta WHERE key='parent'").fetchone()[0]
        )
        if not parent_path:
            raise ValueError("delta report requires a temporal child generation")
        parent = Generation(parent_path)
        parent_complete = parent.verify_complete()
        c.execute(
            "ATTACH DATABASE ? AS old", (f"{parent.path.as_uri()}?mode=ro&immutable=1",)
        )
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        counts = Counter(
            {
                key: 0
                for key in (
                    "added_uuid",
                    "deleted_uuid",
                    "existing_changed",
                    "existing_topology_changed",
                    "existing_outcome_changed",
                    "existing_accepted_metadata_changed",
                )
            }
        )
        counts["parent_source_rows"] = c.execute(
            "SELECT count(*) FROM old.ledger WHERE outcome!='deleted'"
        ).fetchone()[0]
        counts["target_source_rows"] = c.execute(
            "SELECT count(*) FROM ledger WHERE outcome!='deleted'"
        ).fetchone()[0]
        raw_fields, game_fields = Counter(), Counter()
        renames = Counter()
        with (output / "source-changes.jsonl").open("x") as witnesses:
            for (
                key,
                topology,
                uuid,
                previous,
                current,
                old_game,
                new_game,
                old_raw,
                new_raw,
            ) in c.execute(
                """
                SELECT d.game_key,d.topology,n.uuid,o.outcome,n.outcome,o.game,n.game,o.raw,n.raw
                FROM changes d JOIN ledger n ON n.game_key=d.game_key
                LEFT JOIN old.ledger o ON o.game_key=d.game_key ORDER BY d.game_key"""
            ):
                category = "existing"
                if previous is None or previous == "deleted":
                    category = "added"
                    counts["added_uuid"] += 1
                    counts[f"added_{current}"] += 1
                elif current == "deleted":
                    category = "deleted"
                    counts["deleted_uuid"] += 1
                else:
                    counts["existing_changed"] += 1
                    counts["existing_topology_changed"] += topology
                    counts["existing_outcome_changed"] += previous != current
                changed_fields = []
                if category == "existing":
                    before, after = json.loads(old_raw), json.loads(new_raw)
                    raw_fields.update(
                        k
                        for k in before.keys() | after.keys()
                        if before.get(k) != after.get(k)
                    )
                    if previous == current == "accepted":
                        before, after = json.loads(old_game), json.loads(new_game)
                        changed_fields = sorted(
                            k
                            for k in before.keys() | after.keys()
                            if before.get(k) != after.get(k)
                        )
                        game_fields.update(changed_fields)
                        counts["existing_accepted_metadata_changed"] += (
                            bool(changed_fields) and "move_tokens" not in changed_fields
                        )
                        for seat in ("white_username", "black_username"):
                            if seat in changed_fields:
                                renames[(seat, before[seat], after[seat])] += 1
                witnesses.write(
                    encoded(
                        {
                            "game_key": key,
                            "uuid": uuid,
                            "category": category,
                            "old_outcome": previous,
                            "new_outcome": current,
                            "topology_changed": bool(topology),
                            "metadata_fields": changed_fields,
                        }
                    )
                    + "\n"
                )
        threshold = Counter()
        with (output / "threshold-placements.jsonl").open("x") as witnesses:
            for key, old_count, old_owner, new_count, new_owner in c.execute(
                """
                SELECT t.key,t.old_count,t.old_owner,COALESCE(s.count,0),COALESCE(s.owner_xor,0)
                FROM touched t LEFT JOIN support s ON s.key=t.key
                WHERE (t.old_count=1 AND s.count>=2) OR (t.old_count>=2 AND s.count=1)
                ORDER BY t.key"""
            ):
                kind = "promotion" if old_count == 1 else "demotion"
                threshold[kind + "_placements"] += 1
                witnesses.write(
                    encoded(
                        {
                            "position_key": key.hex(),
                            "kind": kind,
                            "old_count": old_count,
                            "new_count": new_count,
                            "singleton_owner": (
                                old_owner if old_count == 1 else new_owner
                            ),
                        }
                    )
                    + "\n"
                )

        def frontier(payload, schema):
            if payload is None:
                return None
            _, _, transitions, _ = _replay_game(load_game(payload))
            shared = {}
            last = 0
            for ply, transition in enumerate(transitions, 1):
                key = transition[0]
                if key not in shared:
                    row = c.execute(
                        f"SELECT count FROM {schema}.support WHERE key=?", (key,)
                    ).fetchone()
                    shared[key] = row is not None and row[0] >= 2
                if shared[key]:
                    last = ply
            return min(len(transitions), last + 1), len(transitions)

        with (output / "threshold-games.jsonl").open("x") as witnesses:
            for (
                key,
                reason,
                uuid,
                old_game,
                new_game,
                old_edges,
                new_edges,
            ) in c.execute(
                """
                SELECT r.game_key,r.reason,n.uuid,
                  CASE WHEN o.outcome='accepted' THEN o.game END,
                  CASE WHEN n.outcome='accepted' THEN n.game END,
                  r.old_edges,r.new_edges
                FROM repairs r JOIN ledger n ON n.game_key=r.game_key
                LEFT JOIN old.ledger o ON o.game_key=r.game_key
                WHERE r.reason IN ('promotion','demotion') ORDER BY r.game_key"""
            ):
                before, after = frontier(old_game, "old"), frontier(new_game, "main")
                threshold["repaired_owners"] += 1
                extension = bool(before and after and after[0] > before[0])
                new_ending = bool(
                    before and after and before[0] < before[1] and after[0] == after[1]
                )
                threshold["old_game_frontier_extensions"] += extension
                threshold["newly_reached_true_endings"] += new_ending
                threshold["unchanged_frontiers"] += before == after
                witnesses.write(
                    encoded(
                        {
                            "game_key": key,
                            "uuid": uuid,
                            "reason": reason,
                            "old_frontier_and_length": before,
                            "new_frontier_and_length": after,
                            "old_distinct_edges": old_edges,
                            "new_distinct_edges": new_edges,
                            "extension": extension,
                            "new_true_ending": new_ending,
                        }
                    )
                    + "\n"
                )
        exclusions = [
            dict(zip(("uuid", "error", "unchanged"), row))
            for row in c.execute(
                """
            SELECT n.uuid,n.error,n.replay_fingerprint=o.replay_fingerprint AND n.error IS o.error
            FROM ledger n LEFT JOIN old.ledger o ON o.uuid=n.uuid AND o.outcome=n.outcome
            WHERE n.outcome='position_replay_error' ORDER BY n.uuid"""
            )
        ]
        result = {
            "parent": parent_complete,
            "target": complete,
            "source_delta": dict(counts),
            "raw_field_changes": dict(raw_fields),
            "accepted_metadata_fields": dict(game_fields),
            "renames": [
                {"seat": seat, "old": old, "new": new, "games": count}
                for (seat, old, new), count in sorted(renames.items())
            ],
            "threshold_delta": dict(threshold),
            "replay_exclusions": exclusions,
            "report_verification_seconds": time.monotonic() - started,
        }
        (output / "report.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generation", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(report(args.generation, args.output), indent=2, sort_keys=True))
