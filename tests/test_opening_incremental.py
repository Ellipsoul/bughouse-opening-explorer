"""Temporal correctness: every target is independently rebuilt by full replay."""

from dataclasses import asdict, replace
import json
import sqlite3

import pytest

from bughouse_explorer.opening.adapter import AdapterOutcome
from bughouse_explorer.opening.incremental import Generation, Revision
from bughouse_explorer.opening.position_graph_streaming import (
    build_two_pass_position_graph,
)
from opening_fixtures import E4, E5, D4, D5, NF3, game, token


def revisions(games):
    return [Revision.from_game(i, g) for i, g in enumerate(games, 1)]


def test_frontier_promotion_does_not_rewrite_an_unchanged_ledger_revision(tmp_path):
    a = game("a", (E4, E5, NF3))
    b = game("b", (E4, E5, D4))
    parent = Generation.create(tmp_path / "parent", source_fingerprint="parent")
    parent.run(revisions([a]))
    child = Generation.create(
        tmp_path / "child", source_fingerprint="child", parent=parent
    )
    with child.connect() as connection:
        for operation, key in [("INSERT", "NEW"), ("UPDATE", "OLD"), ("DELETE", "OLD")]:
            connection.execute(
                f"""CREATE TRIGGER preserve_revision_{operation.lower()}
                BEFORE {operation} ON ledger WHEN {key}.game_key=1
                BEGIN SELECT RAISE(ABORT,'unchanged ledger revision was rewritten'); END"""
            )
    child.run(revisions([a, b]))
    assert child.metrics()["repairs"]["promotion"] == 1
    compare(tmp_path, "unchanged-ledger", child, [a, b])
    parent.verify_complete()


def test_revisiting_a_source_identity_retains_each_previous_move_revision(tmp_path):
    a = game("a", (E4, E5, NF3))
    b = replace(a, move_tokens=(D4, D5, NF3))
    c = replace(a, move_tokens=(E4, E5, D4))
    parent = None
    for label, source, current in [
        ("a", "source-a", a),
        ("b-first", "source-b", b),
        ("c", "source-c", c),
        ("b-again", "source-b", b),
    ]:
        child = Generation.create(
            tmp_path / label, source_fingerprint=source, parent=parent
        )
        child.run(revisions([current]))
        parent = child
    with child.connect() as connection:
        prior = [
            json.loads(row[0])["move_tokens"]
            for row in connection.execute("SELECT game FROM revisions")
        ]
    assert len(prior) == 3
    assert sorted(prior) == sorted(
        [list(a.move_tokens), list(b.move_tokens), list(c.move_tokens)]
    )
    compare(tmp_path, "revisited", child, [b])


def test_missing_revision_namespace_is_rejected_instead_of_invented(tmp_path):
    generation = Generation.create(tmp_path / "invalid", source_fingerprint="source")
    with generation.connect() as connection:
        connection.execute("DELETE FROM meta WHERE key='generation_identity'")
    with pytest.raises(ValueError, match="incomplete checkpoint metadata: generation_identity"):
        generation.run(revisions([game("a", (E4, E5, NF3))]))
    assert not (generation.directory / "complete.json").exists()


def test_delta_report_enumerates_hidden_extensions_and_metadata(tmp_path):
    import runpy
    from pathlib import Path

    reporter = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts/report_opening_incremental_delta.py")
    )["report"]
    a = game("a", (E4, E5, NF3))
    b = game("b", (E4, E5, D4))
    old = Generation.create(tmp_path / "old", source_fingerprint="old")
    old.run(revisions([a]))
    target = Generation.create(
        tmp_path / "target", source_fingerprint="target", parent=old
    )
    target.run(revisions([replace(a, white_username="renamed"), b]))
    result = reporter(target.directory, tmp_path / "report")
    assert result["source_delta"]["added_uuid"] == 1
    assert result["source_delta"]["existing_accepted_metadata_changed"] == 1
    assert result["threshold_delta"]["repaired_owners"] == 1
    assert result["threshold_delta"]["old_game_frontier_extensions"] == 1
    assert result["threshold_delta"]["newly_reached_true_endings"] == 1
    witness = json.loads((tmp_path / "report/threshold-games.jsonl").read_text())
    assert witness["uuid"] == "a"
    assert witness["old_frontier_and_length"] == [1, 3]
    assert witness["new_frontier_and_length"] == [3, 3]
    old.verify_complete()
    target.verify_complete()


def test_delta_report_does_not_replay_an_excluded_previous_owner_revision(tmp_path):
    import runpy
    from pathlib import Path

    reporter = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts/report_opening_incremental_delta.py")
    )["report"]
    a = game("a", (E4, E5, NF3))
    b = game("b", (E4, E5, D4))
    broken = game("corrected", (E4, token("e2", "e3")))
    other = game("other", (D4, D5, NF3))
    parent = Generation.create(tmp_path / "parent", source_fingerprint="parent")
    parent.run(revisions([a, b, broken, other]))
    corrected = replace(broken, move_tokens=a.move_tokens)
    target = Generation.create(
        tmp_path / "target", source_fingerprint="target", parent=parent
    )
    target.run(revisions([corrected, other]))
    result = reporter(target.directory, tmp_path / "report")
    witnesses = [
        json.loads(line)
        for line in (tmp_path / "report/threshold-games.jsonl").read_text().splitlines()
    ]
    witness = next(row for row in witnesses if row["uuid"] == "corrected")
    assert witness["reason"] == "demotion"
    assert witness["old_frontier_and_length"] is None
    assert witness["new_frontier_and_length"] == [1, 3]
    assert not witness["extension"]
    assert result["source_delta"]["deleted_uuid"] == 2
    assert result["replay_exclusions"] == []
    compare(tmp_path, "corrected-owner", target, [corrected, other])


def compare(tmp_path, name, generation, games):
    export = tmp_path / (name + "-incremental")
    generation.export(export)
    full = tmp_path / (name + "-full")
    rows = [AdapterOutcome(i, g) for i, g in enumerate(games, 1)]
    build_two_pass_position_graph(
        lambda: iter(rows),
        full,
        source_fingerprint=generation.source_fingerprint,
        temporary_directory=tmp_path / (name + "-scratch"),
    )
    assert {p.name: p.read_bytes() for p in export.iterdir()} == {
        p.name: p.read_bytes() for p in full.iterdir()
    }


def test_hidden_promotion_demotion_and_owner_replacement(tmp_path):
    a = game("a", (E4, E5, NF3))
    b = game("b", (E4, E5, D4))
    c = game("c", (D4, D5, NF3))
    prior = None
    for i, games in enumerate(([a, c], [a, b, c], [b, c], [a, c])):
        gen = Generation.create(
            tmp_path / str(i), source_fingerprint=str(i), parent=prior
        )
        gen.run(revisions(games))
        compare(tmp_path, str(i), gen, games)
        prior = gen


def test_metadata_change_without_content_hash_and_source_reordering(tmp_path):
    a = game("a", (E4, E5, NF3))
    b = game("b", (E4, E5, D4))
    old = Generation.create(tmp_path / "old", source_fingerprint="old")
    old.run(revisions([a, b]))
    corrected = replace(
        a,
        white_username="renamed",
        white_rating=1234,
        white_result="resigned",
        black_result="win",
        source="callback",
        provenance_flags=("callback_source",),
    )
    new = Generation.create(tmp_path / "new", source_fingerprint="new", parent=old)
    new.run(revisions([b, corrected]))
    compare(tmp_path, "metadata", new, [b, corrected])
    assert new.metrics()["support_replayed_games"] == 0


def test_cycles_transpositions_endings_and_atomic_malformed_exclusion(tmp_path):
    nf6 = token("g8", "f6")
    nc3 = token("b1", "c3")
    nc6 = token("b8", "c6")
    cycle = (NF3, nf6, token("f3", "g1"), token("f6", "g8"))
    a = game("a", cycle + (E4, E5))
    b = game("b", (nc3, nc6, NF3, nf6, E4))
    c = game("c", (NF3, nf6, nc3, nc6, D4))
    broken = game("broken", (E4, token("e2", "e3")))
    gen = Generation.create(tmp_path / "base", source_fingerprint="cycle")
    gen.run(revisions([a, b, c, broken]))
    compare(tmp_path, "cycle", gen, [a, b, c, broken])
    assert gen.metrics()["skipped"] == {"position_replay_error": 1}


@pytest.mark.parametrize("stage", ["ingest", "support", "repair", "verify", "complete"])
def test_interruption_resume_and_noop_are_identical(tmp_path, stage):
    games = [game("a", (E4, E5, NF3)), game("b", (E4, E5, D4))]
    gen = Generation.create(tmp_path / "resume", source_fingerprint="resume")
    with pytest.raises(InterruptedError):
        gen.run(revisions(games), interrupt_after=stage)
    gen = Generation.open(tmp_path / "resume", source_fingerprint="resume")
    gen.run(revisions(games))
    gen.run(revisions(games))
    compare(tmp_path, "resume", gen, games)
    with pytest.raises(ValueError, match="source"):
        Generation.open(tmp_path / "resume", source_fingerprint="wrong")


def test_move_correction_prunes_orphans_and_admission_changes(tmp_path):
    a = game("a", (E4, E5, NF3))
    b = game("b", (E4, E5, D4))
    original = Generation.create(tmp_path / "original", source_fingerprint="original")
    original.run(revisions([a, b]))
    changed = replace(b, move_tokens=(D4, D5, NF3))
    next_gen = Generation.create(
        tmp_path / "changed", source_fingerprint="changed", parent=original
    )
    next_gen.run(revisions([a, changed]))
    compare(tmp_path, "changed", next_gen, [a, changed])
    rejected = Revision(2, b.uuid, "excluded", None, "empty_tcn", "empty")
    excluded = Generation.create(
        tmp_path / "excluded", source_fingerprint="excluded", parent=next_gen
    )
    excluded.run([Revision.from_game(1, a), rejected])
    out = tmp_path / "excluded-output"
    excluded.export(out)
    assert json.loads((out / "manifest.json").read_text())["games"] == 1
    restored = Generation.create(
        tmp_path / "restored", source_fingerprint="restored", parent=excluded
    )
    restored.run(revisions([a, b]))
    compare(tmp_path, "restored", restored, [a, b])


def test_split_batches_and_reordered_ingestion_reach_same_target(tmp_path):
    a = game("a", (E4, E5, NF3))
    b = game("b", (E4, E5, D4))
    c = game("c", (D4, D5, NF3))
    base = Generation.create(tmp_path / "base", source_fingerprint="base")
    base.run(revisions([a]))
    for label, intermediate in [("forward", [a, b]), ("reverse", [c, a])]:
        middle = Generation.create(
            tmp_path / label, source_fingerprint=label, parent=base
        )
        middle.run(revisions(intermediate))
        final = Generation.create(
            tmp_path / (label + "-final"), source_fingerprint="target", parent=middle
        )
        final.run(revisions([b, a, c]))
        compare(tmp_path, label, final, [b, a, c])


def test_parent_stays_valid_and_policy_mismatch_fails_closed(tmp_path):
    a = game("a", (E4, E5, NF3))
    b = game("b", (E4, E5, D4))
    base = Generation.create(tmp_path / "base", source_fingerprint="base")
    base.run(revisions([a]))
    before = base.path.read_bytes()
    child = Generation.create(
        tmp_path / "child", source_fingerprint="child", parent=base
    )
    child.run(revisions([a, b]))
    assert base.path.read_bytes() == before
    base.verify_complete()
    with child.connect() as c:
        child.set(c, "policy", {"schema": "wrong"})
    with pytest.raises(ValueError, match="policy"):
        Generation.open(child.directory, source_fingerprint="child")


@pytest.mark.parametrize("stage", ["ingest", "support", "repair", "verify"])
def test_temporal_update_interruption_preserves_parent_and_parity(tmp_path, stage):
    a = game("a", (E4, E5, NF3))
    b = game("b", (E4, E5, D4))
    base = Generation.create(tmp_path / "base", source_fingerprint="base")
    base.run(revisions([a]))
    child = Generation.create(
        tmp_path / "child", source_fingerprint="target", parent=base
    )
    with pytest.raises(InterruptedError):
        child.run(revisions([a, b]), interrupt_after=stage)
    base.verify_complete()
    child.run(revisions([a, b]))
    compare(tmp_path, "resumed", child, [a, b])


def test_interruption_between_old_subtraction_and_new_support_is_atomic(
    tmp_path, monkeypatch
):
    import bughouse_explorer.opening.incremental as module

    a = game("a", (E4, E5, NF3))
    b = game("b", (E4, E5, D4))
    parent = Generation.create(tmp_path / "old", source_fingerprint="old")
    parent.run(revisions([a, b]))
    corrected = replace(a, move_tokens=(D4, D5, NF3))
    child = Generation.create(tmp_path / "new", source_fingerprint="new", parent=parent)
    with pytest.raises(InterruptedError):
        child.run(revisions([corrected, b]), interrupt_after="ingest")
    original = module._replay_game
    calls = 0

    def interrupted(game):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise InterruptedError("old revision subtracted, new not added")
        return original(game)

    monkeypatch.setattr(module, "_replay_game", interrupted)
    with pytest.raises(InterruptedError):
        child.run(revisions([corrected, b]))
    with parent.connect() as p, child.connect() as c:
        assert list(p.execute("SELECT * FROM support ORDER BY key")) == list(
            c.execute("SELECT * FROM support ORDER BY key")
        )
    monkeypatch.setattr(module, "_replay_game", original)
    child.run(revisions([corrected, b]))
    compare(tmp_path, "support-atomic", child, [corrected, b])
    parent.verify_complete()


def test_interruption_inside_frontier_replacement_restores_old_facts(
    tmp_path, monkeypatch
):
    a = game("a", (E4, E5, NF3))
    b = game("b", (E4, E5, D4))
    parent = Generation.create(tmp_path / "old", source_fingerprint="old")
    parent.run(revisions([a]))
    child = Generation.create(tmp_path / "new", source_fingerprint="new", parent=parent)
    with pytest.raises(InterruptedError):
        child.run(revisions([a, b]), interrupt_after="support")
    original = Generation._materialize

    def interrupted(self, connection, key, game):
        original(self, connection, key, game)
        raise InterruptedError("replacement facts written before cursor commit")

    monkeypatch.setattr(Generation, "_materialize", interrupted)
    with pytest.raises(InterruptedError):
        child.run(revisions([a, b]))
    with parent.connect() as p, child.connect() as c:
        for table in (
            "position_games",
            "state_games",
            "edge_games",
            "endings",
            "posting_entries",
        ):
            assert list(p.execute(f"SELECT * FROM {table} ORDER BY 1,2")) == list(
                c.execute(f"SELECT * FROM {table} ORDER BY 1,2")
            )
    monkeypatch.setattr(Generation, "_materialize", original)
    child.run(revisions([a, b]))
    compare(tmp_path, "repair-atomic", child, [a, b])
    parent.verify_complete()


def test_busy_wal_checkpoint_cannot_publish_a_completion_manifest(tmp_path):
    games = [game("a", (E4, E5, NF3)), game("b", (E4, E5, D4))]
    gen = Generation.create(tmp_path / "gen", source_fingerprint="busy")
    with pytest.raises(InterruptedError):
        gen.run(revisions(games), interrupt_after="ingest")
    reader = sqlite3.connect(f"{gen.path.as_uri()}?mode=ro", uri=True)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT count(*) FROM incoming").fetchone()
        with pytest.raises(ValueError, match="active reader"):
            gen.run(revisions(games))
        assert not (gen.directory / "complete.json").exists()
    finally:
        reader.close()
    gen.run(revisions(games))
    gen.verify_complete()
    compare(tmp_path, "busy-resumed", gen, games)


def test_final_batch_unchanged_support_replaces_owner(tmp_path):
    a = game("a", (E4, E5, NF3))
    b = game("b", (E4, E5, D4))
    base = Generation.create(tmp_path / "base", source_fingerprint="base")
    base.run(revisions([a]))
    target = Generation.create(
        tmp_path / "target", source_fingerprint="target", parent=base
    )
    target.run(revisions([b]))
    compare(tmp_path, "owner", target, [b])
    with target.connect() as c:
        key = c.execute("SELECT game_key FROM ledger WHERE uuid='b'").fetchone()[0]
        assert not c.execute(
            "SELECT 1 FROM support WHERE count=1 AND owner_xor!=?", (key,)
        ).fetchone()


def test_duplicate_uuid_and_incomplete_parent_fail_closed(tmp_path):
    a = game("a", (E4, E5, NF3))
    base = Generation.create(tmp_path / "base", source_fingerprint="base")
    with pytest.raises(sqlite3.IntegrityError):
        base.run(revisions([a, a]))
    with pytest.raises(ValueError, match="incomplete"):
        Generation.create(tmp_path / "bad-child", source_fingerprint="bad", parent=base)


def test_checked_staging_seed_matches_full_then_updates(tmp_path):
    from bughouse_explorer.opening.incremental import validate_materialized_seed

    a = game("a", (E4, E5, NF3))
    b = game("b", (E4, E5, D4))
    full = tmp_path / "old-full"
    scratch = tmp_path / "old-scratch"
    build_two_pass_position_graph(
        lambda: iter([AdapterOutcome(1, a)]),
        full,
        source_fingerprint="old",
        temporary_directory=scratch,
    )
    staging = scratch / "graph-staging/opening-position-graph.sqlite3"
    original = staging.read_bytes()
    validate_materialized_seed(staging, full, tmp_path / "seed-proof")
    gen = Generation.create(tmp_path / "old", source_fingerprint="old")
    gen.configure_seed(tmp_path / "seed-proof/validated-seed.json")
    gen.run(revisions([a]))
    compare(tmp_path, "seeded", gen, [a])
    child = Generation.create(tmp_path / "new", source_fingerprint="new", parent=gen)
    child.run(revisions([a, b]))
    compare(tmp_path, "seeded-update", child, [a, b])
    assert staging.read_bytes() == original


def test_deleted_uuid_retains_its_key_across_new_games_and_reappearance(tmp_path):
    a = game("a", (E4, E5, NF3))
    b = game("b", (E4, E5, D4))
    c = game("c", (D4, D5, NF3))
    parent = None
    keys = {}
    for i, games in enumerate(([a, b], [a], [a, c], [b, a, c])):
        gen = Generation.create(
            tmp_path / str(i), source_fingerprint=str(i), parent=parent
        )
        gen.run(revisions(games))
        compare(tmp_path, f"keys-{i}", gen, games)
        with gen.connect() as connection:
            for uuid, key in connection.execute("SELECT uuid,game_key FROM ledger"):
                if uuid in keys:
                    assert key == keys[uuid]
                else:
                    keys[uuid] = key
        parent = gen
    assert len(set(keys.values())) == 3


def test_discovery_spill_resume_and_corruption_fail_closed(tmp_path, monkeypatch):
    import bughouse_explorer.opening.incremental as module

    monkeypatch.setattr(module, "SUPPORT_RECORDS_PER_CHUNK", 2)
    games = [game("a", (E4, E5, NF3)), game("b", (E4, E5, D4))]
    gen = Generation.create(tmp_path / "gen", source_fingerprint="spill")

    def interrupt(event):
        if event["stage"] == "support_discovery":
            raise InterruptedError("spill committed")

    with pytest.raises(InterruptedError):
        gen.run(revisions(games), progress=interrupt)
    spill = next(gen.directory.glob("support-*.bin"))
    original = spill.read_bytes()
    spill.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        gen.run(revisions(games))
    spill.write_bytes(original)
    gen.run(revisions(games))
    compare(tmp_path, "spill", gen, games)


def test_export_interruption_keeps_generation_valid_and_requires_fresh_output(
    tmp_path, monkeypatch
):
    import bughouse_explorer.opening.incremental as module

    games = [game("a", (E4, E5, NF3))]
    gen = Generation.create(tmp_path / "gen", source_fingerprint="export")
    gen.run(revisions(games))
    original = module.export_graph_facts

    def interrupt(*args, **kwargs):
        raise InterruptedError("export")

    monkeypatch.setattr(module, "export_graph_facts", interrupt)
    with pytest.raises(InterruptedError):
        gen.export(tmp_path / "partial")
    assert not (tmp_path / "partial/manifest.json").exists()
    gen.verify_complete()
    monkeypatch.setattr(module, "export_graph_facts", original)
    with pytest.raises(FileExistsError):
        gen.export(tmp_path / "partial")
    compare(tmp_path, "retry", gen, games)


def test_seed_copy_resumes_at_a_committed_table(tmp_path):
    from bughouse_explorer.opening.incremental import validate_materialized_seed

    games = [game("a", (E4, E5, NF3)), game("b", (E4, E5, D4))]
    full = tmp_path / "full"
    scratch = tmp_path / "scratch"
    build_two_pass_position_graph(
        lambda: iter([AdapterOutcome(i, g) for i, g in enumerate(games)]),
        full,
        source_fingerprint="seed-resume",
        temporary_directory=scratch,
    )
    validate_materialized_seed(
        scratch / "graph-staging/opening-position-graph.sqlite3",
        full,
        tmp_path / "proof",
    )
    gen = Generation.create(tmp_path / "gen", source_fingerprint="seed-resume")
    gen.configure_seed(tmp_path / "proof/validated-seed.json")

    def interrupt(event):
        if event["stage"] == "seed_materialized":
            raise InterruptedError("table committed")

    with pytest.raises(InterruptedError):
        gen.run(revisions(games), progress=interrupt)
    gen.run(revisions(games))
    compare(tmp_path, "seed-resume", gen, games)


def test_owner_corruption_is_not_silently_accepted(tmp_path):
    a = game("a", (E4, E5, NF3))
    b = game("b", (D4, D5, NF3))
    base = Generation.create(tmp_path / "base", source_fingerprint="base")
    base.run(revisions([a]))
    child = Generation.create(
        tmp_path / "child", source_fingerprint="child", parent=base
    )
    with pytest.raises(InterruptedError):
        child.run(revisions([a, b]), interrupt_after="repair")
    with child.connect() as c:
        c.execute("UPDATE support SET owner_xor=123456 WHERE count>=2")
    with pytest.raises(ValueError, match="accumulator"):
        child.run(revisions([a, b]))
    assert not (child.directory / "complete.json").exists()
    base.verify_complete()


def test_long_repeated_bridge_extends_to_a_true_ending(tmp_path):
    cycle = (NF3, token("g8", "f6"), token("f3", "g1"), token("f6", "g8"))
    a = game("a", cycle * 20 + (E4, E5))
    b = game("b", (E4, E5, D4))
    base = Generation.create(tmp_path / "base", source_fingerprint="base")
    base.run(revisions([a]))
    child = Generation.create(
        tmp_path / "child", source_fingerprint="bridge", parent=base
    )
    child.run(revisions([a, b]))
    compare(tmp_path, "long-bridge", child, [a, b])
    with child.connect() as c:
        assert c.execute("SELECT count(*) FROM endings").fetchone()[0] == 2


def test_ingest_restarts_after_a_committed_batch_without_duplicate_games(tmp_path):
    games = [game(str(i), (E4,)) for i in range(1001)]
    gen = Generation.create(tmp_path / "gen", source_fingerprint="batch")

    def interrupted_rows():
        yield from revisions(games[:1000])
        raise InterruptedError("after first durable batch")

    with pytest.raises(InterruptedError):
        gen.run(interrupted_rows())
    with gen.connect() as c:
        assert gen.get(c, "ingest_cursor") == 1000
        assert c.execute("SELECT count(*) FROM incoming").fetchone()[0] == 1000
    gen.run(revisions(games))
    compare(tmp_path, "batch", gen, games)
