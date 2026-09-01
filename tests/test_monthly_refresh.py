import hashlib
import json
import sqlite3
from dataclasses import dataclass

import pytest

from bughouse_explorer.monthly_refresh import (
    PLAYER_INSIGHT_PROJECTIONS,
    ProjectionSpec,
    ProjectionReport,
    build_player_insights_artifact,
    create_checked_crawler_snapshot,
    publish_staged_projections,
    stage_player_insight_projections,
    summarize_crawler_database,
)


def _create_crawler_database(path, *, queued_jobs=0):
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE players (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL,
                tracking_started_at INTEGER,
                full_crawl_completed_at INTEGER,
                archive_unavailable_at INTEGER
            );
            CREATE TABLE games (
                uuid TEXT PRIMARY KEY
            );
            CREATE TABLE game_participants (
                game_uuid TEXT NOT NULL REFERENCES games(uuid),
                player_id INTEGER NOT NULL REFERENCES players(id),
                PRIMARY KEY (game_uuid, player_id)
            );
            CREATE TABLE crawl_jobs (
                id INTEGER PRIMARY KEY,
                status TEXT NOT NULL
            );
            CREATE TABLE crawl_runs (
                id TEXT PRIMARY KEY,
                run_type TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at INTEGER NOT NULL,
                ended_at INTEGER
            );
            INSERT INTO players VALUES (
                1, 'alice', 'eligible', 1700000000, 1700000001, NULL
            );
            INSERT INTO games VALUES ('game-1');
            INSERT INTO game_participants VALUES ('game-1', 1);
            INSERT INTO crawl_runs VALUES ('run-1', 'monthly', 'complete', 1, 2);
            """
        )
        connection.executemany(
            "INSERT INTO crawl_jobs(status) VALUES ('queued')",
            [() for _ in range(queued_jobs)],
        )


def test_checked_snapshot_refuses_an_incomplete_crawler(tmp_path):
    crawler = tmp_path / "crawler.db"
    snapshot = tmp_path / "snapshot.db"
    _create_crawler_database(crawler, queued_jobs=1)

    with pytest.raises(ValueError, match="crawler closure is incomplete"):
        create_checked_crawler_snapshot(crawler, snapshot)

    assert not snapshot.exists()


def test_crawler_summary_records_cohort_discovery_and_closure_state(tmp_path):
    crawler = tmp_path / "crawler.db"
    _create_crawler_database(crawler)

    summary = summarize_crawler_database(crawler)

    assert summary.games == 1
    assert summary.participants == 1
    assert summary.players == 1
    assert summary.permanently_tracked_players == 1
    assert summary.fully_crawled_players == 1
    assert summary.player_states == {"eligible": 1}
    assert summary.job_states == {}
    assert summary.closure_ready is True
    assert summary.latest_run_id == "run-1"
    assert summary.latest_run_status == "complete"


def test_checked_snapshot_is_an_independent_validated_online_backup(tmp_path):
    crawler = tmp_path / "crawler.db"
    snapshot = tmp_path / "snapshot.db"
    _create_crawler_database(crawler)

    report = create_checked_crawler_snapshot(crawler, snapshot)

    assert snapshot.is_file()
    assert report.snapshot_path == str(snapshot.resolve())
    assert len(report.snapshot_sha256) == 64
    assert report.snapshot_bytes == snapshot.stat().st_size
    assert report.quick_check == "ok"
    assert report.foreign_key_violations == 0
    assert report.games == 1
    assert report.participants == 1
    assert report.tracked_players == 1
    assert report.latest_run_id == "run-1"
    assert report.latest_run_status == "complete"

    with sqlite3.connect(crawler) as connection:
        connection.execute("INSERT INTO games VALUES ('game-2')")

    with sqlite3.connect(f"file:{snapshot}?mode=ro&immutable=1", uri=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1


def test_checked_snapshot_refuses_a_running_crawl_even_before_jobs_are_queued(tmp_path):
    crawler = tmp_path / "crawler.db"
    snapshot = tmp_path / "snapshot.db"
    _create_crawler_database(crawler)
    with sqlite3.connect(crawler) as connection:
        connection.execute("UPDATE crawl_runs SET status = 'running', ended_at = NULL")

    with pytest.raises(ValueError, match="active_runs"):
        create_checked_crawler_snapshot(crawler, snapshot)

    assert not snapshot.exists()


def test_projection_staging_exports_every_registered_insight_twice(tmp_path):
    database = tmp_path / "insights.db"
    database.write_bytes(b"checked database")
    output = tmp_path / "projections"
    calls = []

    def exporter(label):
        def export(_database, path, *, replace=False):
            assert replace is False
            calls.append(label)
            path.write_text(f"{label}\n")
        return export

    reports = stage_player_insight_projections(
        database,
        output,
        specs=(
            ProjectionSpec("alpha", "alpha.json", exporter("alpha")),
            ProjectionSpec("beta", "beta.json", exporter("beta")),
        ),
    )

    assert calls == ["alpha", "alpha", "beta", "beta"]
    assert [report.name for report in reports] == ["alpha", "beta"]
    assert [report.filename for report in reports] == ["alpha.json", "beta.json"]
    assert (output / "alpha.json").read_text() == "alpha\n"
    assert (output / "beta.json").read_text() == "beta\n"
    assert all(len(report.sha256) == 64 for report in reports)


def test_monthly_registry_contains_every_current_player_insight_projection():
    assert [spec.filename for spec in PLAYER_INSIGHT_PROJECTIONS] == [
        "player-material-insights.json",
        "player-king-height-insights.json",
        "player-drop-heatmap-insights.json",
        "player-material-game-highs.json",
    ]


def test_projection_publication_validates_every_file_before_replacing_any(tmp_path):
    staging = tmp_path / "staging"
    frontend = tmp_path / "frontend"
    staging.mkdir()
    frontend.mkdir()
    (staging / "alpha.json").write_text("new alpha\n")
    (staging / "beta.json").write_text("new beta\n")
    (frontend / "alpha.json").write_text("old alpha\n")
    (frontend / "beta.json").write_text("old beta\n")
    reports = tuple(
        ProjectionReport(
            name=name,
            filename=f"{name}.json",
            bytes=(staging / f"{name}.json").stat().st_size,
            sha256=hashlib.sha256(
                (staging / f"{name}.json").read_bytes()
            ).hexdigest(),
        )
        for name in ("alpha", "beta")
    )
    (staging / "beta.json").write_text("tampered\n")

    with pytest.raises(ValueError, match="beta"):
        publish_staged_projections(staging, frontend, reports)

    assert (frontend / "alpha.json").read_text() == "old alpha\n"
    assert (frontend / "beta.json").read_text() == "old beta\n"


def test_projection_publication_replaces_the_validated_set(tmp_path):
    staging = tmp_path / "staging"
    frontend = tmp_path / "frontend"
    staging.mkdir()
    frontend.mkdir()
    for name in ("alpha", "beta"):
        (staging / f"{name}.json").write_text(f"new {name}\n")
        (frontend / f"{name}.json").write_text(f"old {name}\n")
    reports = tuple(
        ProjectionReport(
            name=name,
            filename=f"{name}.json",
            bytes=(staging / f"{name}.json").stat().st_size,
            sha256=hashlib.sha256(
                (staging / f"{name}.json").read_bytes()
            ).hexdigest(),
        )
        for name in ("alpha", "beta")
    )

    published = publish_staged_projections(staging, frontend, reports)

    assert published == (
        str(frontend / "alpha.json"),
        str(frontend / "beta.json"),
    )
    assert (frontend / "alpha.json").read_text() == "new alpha\n"
    assert (frontend / "beta.json").read_text() == "new beta\n"


def test_player_insights_artifact_builds_once_and_stages_registered_exports(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    snapshot.write_bytes(b"immutable source")
    snapshot_sha256 = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    artifact = tmp_path / "artifact"
    builder_calls = []

    @dataclass(frozen=True)
    class FakeBuildReport:
        dataset_version: str
        tracked_players: int

    def builder(source, output, *, snapshot_sha256, progress, progress_interval):
        builder_calls.append((source, snapshot_sha256, progress_interval))
        with sqlite3.connect(output) as connection:
            connection.execute(
                "CREATE TABLE insight_builds (dataset_version TEXT PRIMARY KEY)"
            )
            connection.execute("INSERT INTO insight_builds VALUES ('dataset-1')")
        if progress:
            progress({"processed_games": 1})
        return FakeBuildReport("dataset-1", 1)

    def exporter(_database, path, *, replace=False):
        path.write_text('{"dataset":"dataset-1"}\n')

    progress = []
    report = build_player_insights_artifact(
        snapshot,
        snapshot_sha256,
        artifact,
        builder=builder,
        specs=(ProjectionSpec("alpha", "alpha.json", exporter),),
        progress=progress.append,
        progress_interval=10,
    )

    assert builder_calls == [(snapshot.resolve(), snapshot_sha256, 10)]
    assert progress == [{"processed_games": 1}]
    assert report.dataset_version == "dataset-1"
    assert report.database_sha256 == hashlib.sha256(
        (artifact / "player-insights.db").read_bytes()
    ).hexdigest()
    assert report.quick_check == "ok"
    assert report.foreign_key_violations == 0
    assert [item.filename for item in report.projections] == ["alpha.json"]
    result = json.loads((artifact / "monthly-refresh-result.json").read_text())
    assert result["build"]["tracked_players"] == 1
    assert result["projections"][0]["filename"] == "alpha.json"
