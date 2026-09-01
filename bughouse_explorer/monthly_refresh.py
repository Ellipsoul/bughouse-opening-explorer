"""Checked snapshot and publication primitives for the monthly data refresh."""

from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
import os
from pathlib import Path
import resource
import sqlite3
import tempfile
import time
from typing import Callable

from .insights.export import (
    export_drop_heatmap_insights,
    export_king_height_insights,
    export_material_game_highs,
    export_material_insights,
)
from .insights.material import build_material_insights


@dataclass(frozen=True)
class CrawlerSnapshotReport:
    snapshot_path: str
    snapshot_sha256: str
    snapshot_bytes: int
    quick_check: str
    foreign_key_violations: int
    games: int
    participants: int
    tracked_players: int
    latest_run_id: str | None
    latest_run_status: str | None


@dataclass(frozen=True)
class CrawlerSummary:
    games: int
    participants: int
    players: int
    permanently_tracked_players: int
    fully_crawled_players: int
    player_states: dict[str, int]
    job_states: dict[str, int]
    closure_ready: bool
    closure: dict[str, int]
    latest_run_id: str | None
    latest_run_status: str | None


@dataclass(frozen=True)
class ProjectionSpec:
    name: str
    filename: str
    exporter: Callable


@dataclass(frozen=True)
class ProjectionReport:
    name: str
    filename: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class PlayerInsightsArtifactReport:
    artifact_directory: str
    database_path: str
    database_sha256: str
    database_bytes: int
    dataset_version: str
    quick_check: str
    foreign_key_violations: int
    build_seconds: float
    projections: tuple[ProjectionReport, ...]
    result_path: str


PLAYER_INSIGHT_PROJECTIONS = (
    ProjectionSpec(
        "material",
        "player-material-insights.json",
        export_material_insights,
    ),
    ProjectionSpec(
        "king-height",
        "player-king-height-insights.json",
        export_king_height_insights,
    ),
    ProjectionSpec(
        "drop-heatmap",
        "player-drop-heatmap-insights.json",
        export_drop_heatmap_insights,
    ),
    ProjectionSpec(
        "material-game-highs",
        "player-material-game-highs.json",
        export_material_game_highs,
    ),
)


def _closure_counts_connection(connection: sqlite3.Connection) -> dict[str, int]:
    remaining_jobs = connection.execute(
        """
        SELECT COUNT(*) FROM crawl_jobs
        WHERE status IN ('queued', 'leased', 'deferred')
        """
    ).fetchone()[0]
    failed_jobs = connection.execute(
        "SELECT COUNT(*) FROM crawl_jobs WHERE status = 'failed'"
    ).fetchone()[0]
    tracked_without_outcome = connection.execute(
        """
        SELECT COUNT(*) FROM players
        WHERE tracking_started_at IS NOT NULL
          AND full_crawl_completed_at IS NULL
          AND archive_unavailable_at IS NULL
        """
    ).fetchone()[0]
    active_runs = connection.execute(
        "SELECT COUNT(*) FROM crawl_runs WHERE status = 'running'"
    ).fetchone()[0]
    return {
        "remaining_jobs": remaining_jobs,
        "failed_jobs": failed_jobs,
        "tracked_without_outcome": tracked_without_outcome,
        "active_runs": active_runs,
    }


def _closure_counts(database_path: Path) -> dict[str, int]:
    with sqlite3.connect(database_path) as connection:
        return _closure_counts_connection(connection)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize_crawler_database(database_path: str | Path) -> CrawlerSummary:
    """Return the small, read-only before/after summary used by monthly evidence."""
    database_path = Path(database_path).resolve()
    with sqlite3.connect(database_path) as connection:
        games = connection.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        participants = connection.execute(
            "SELECT COUNT(*) FROM game_participants"
        ).fetchone()[0]
        players = connection.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        permanently_tracked_players = connection.execute(
            "SELECT COUNT(*) FROM players WHERE tracking_started_at IS NOT NULL"
        ).fetchone()[0]
        fully_crawled_players = connection.execute(
            "SELECT COUNT(*) FROM players WHERE full_crawl_completed_at IS NOT NULL"
        ).fetchone()[0]
        player_states = dict(
            connection.execute(
                "SELECT state, COUNT(*) FROM players GROUP BY state ORDER BY state"
            ).fetchall()
        )
        job_states = dict(
            connection.execute(
                "SELECT status, COUNT(*) FROM crawl_jobs GROUP BY status ORDER BY status"
            ).fetchall()
        )
        latest_run = connection.execute(
            "SELECT id, status FROM crawl_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    closure = _closure_counts(database_path)
    return CrawlerSummary(
        games=games,
        participants=participants,
        players=players,
        permanently_tracked_players=permanently_tracked_players,
        fully_crawled_players=fully_crawled_players,
        player_states=player_states,
        job_states=job_states,
        closure_ready=not any(closure.values()),
        closure=closure,
        latest_run_id=latest_run[0] if latest_run else None,
        latest_run_status=latest_run[1] if latest_run else None,
    )


def _write_json_atomically(path: Path, payload: dict) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _inspect_snapshot(snapshot_path: Path) -> CrawlerSnapshotReport:
    source_uri = f"file:{snapshot_path}?mode=ro&immutable=1"
    with sqlite3.connect(source_uri, uri=True) as connection:
        closure = _closure_counts_connection(connection)
        if any(closure.values()):
            raise ValueError(f"snapshot closure is incomplete: {closure}")
        quick_check_rows = connection.execute("PRAGMA quick_check").fetchall()
        if quick_check_rows != [("ok",)]:
            raise ValueError(f"snapshot quick_check failed: {quick_check_rows[:10]}")
        foreign_key_violations = sum(
            1 for _ in connection.execute("PRAGMA foreign_key_check")
        )
        if foreign_key_violations:
            raise ValueError(
                f"snapshot has {foreign_key_violations} foreign-key violation(s)"
            )
        games = connection.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        participants = connection.execute(
            "SELECT COUNT(*) FROM game_participants"
        ).fetchone()[0]
        tracked_players = connection.execute(
            "SELECT COUNT(*) FROM players WHERE tracking_started_at IS NOT NULL"
        ).fetchone()[0]
        latest_run = connection.execute(
            """
            SELECT id, status FROM crawl_runs
            ORDER BY started_at DESC LIMIT 1
            """
        ).fetchone()
    return CrawlerSnapshotReport(
        snapshot_path=str(snapshot_path),
        snapshot_sha256=_sha256(snapshot_path),
        snapshot_bytes=snapshot_path.stat().st_size,
        quick_check="ok",
        foreign_key_violations=0,
        games=games,
        participants=participants,
        tracked_players=tracked_players,
        latest_run_id=latest_run[0] if latest_run else None,
        latest_run_status=latest_run[1] if latest_run else None,
    )


def create_checked_crawler_snapshot(
    crawler_database: str | Path,
    snapshot_path: str | Path,
) -> CrawlerSnapshotReport:
    """Create a SQLite online backup only after the durable crawler is closed."""
    crawler_database = Path(crawler_database).resolve()
    snapshot_path = Path(snapshot_path).resolve()
    closure = _closure_counts(crawler_database)
    if any(closure.values()):
        raise ValueError(f"crawler closure is incomplete: {closure}")
    if snapshot_path.exists():
        raise FileExistsError(snapshot_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{snapshot_path.name}.",
        suffix=".tmp",
        dir=snapshot_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.unlink()
    try:
        with sqlite3.connect(crawler_database) as source:
            source.execute("PRAGMA query_only = ON")
            with sqlite3.connect(temporary_path) as destination:
                source.backup(destination)
        temporary_report = _inspect_snapshot(temporary_path)
        os.replace(temporary_path, snapshot_path)
        return CrawlerSnapshotReport(
            **{
                **temporary_report.__dict__,
                "snapshot_path": str(snapshot_path),
            }
        )
    finally:
        temporary_path.unlink(missing_ok=True)


def stage_player_insight_projections(
    insights_database: str | Path,
    output_directory: str | Path,
    *,
    specs: tuple[ProjectionSpec, ...] = PLAYER_INSIGHT_PROJECTIONS,
) -> tuple[ProjectionReport, ...]:
    """Export and independently repeat every registered browser projection."""
    insights_database = Path(insights_database).resolve()
    output_directory = Path(output_directory).resolve()
    if output_directory.exists():
        raise FileExistsError(output_directory)
    output_directory.mkdir(parents=True)

    reports = []
    with tempfile.TemporaryDirectory(prefix="player-insights-export-check-") as name:
        verification_directory = Path(name)
        for spec in specs:
            output_path = output_directory / spec.filename
            verification_path = verification_directory / spec.filename
            spec.exporter(insights_database, output_path, replace=False)
            spec.exporter(insights_database, verification_path, replace=False)
            output_sha256 = _sha256(output_path)
            verification_sha256 = _sha256(verification_path)
            if output_sha256 != verification_sha256:
                raise ValueError(f"projection {spec.name} is not deterministic")
            reports.append(
                ProjectionReport(
                    name=spec.name,
                    filename=spec.filename,
                    bytes=output_path.stat().st_size,
                    sha256=output_sha256,
                )
            )
    return tuple(reports)


def publish_staged_projections(
    staging_directory: str | Path,
    frontend_data_directory: str | Path,
    reports: tuple[ProjectionReport, ...],
) -> tuple[str, ...]:
    """Validate the complete staged set, then atomically replace each web file."""
    staging_directory = Path(staging_directory).resolve()
    frontend_data_directory = Path(frontend_data_directory).resolve()

    for report in reports:
        if Path(report.filename).name != report.filename:
            raise ValueError(f"invalid projection filename: {report.filename}")
        source = staging_directory / report.filename
        if not source.is_file():
            raise ValueError(f"projection {report.name} is missing")
        if (
            source.stat().st_size != report.bytes
            or _sha256(source) != report.sha256
        ):
            raise ValueError(f"projection {report.name} failed checksum validation")

    frontend_data_directory.mkdir(parents=True, exist_ok=True)
    temporary_targets = []
    try:
        for report in reports:
            source = staging_directory / report.filename
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{report.filename}.",
                suffix=".tmp",
                dir=frontend_data_directory,
            )
            temporary_path = Path(temporary_name)
            with source.open("rb") as input_stream, os.fdopen(
                descriptor, "wb"
            ) as output_stream:
                for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
                    output_stream.write(chunk)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            temporary_targets.append(
                (temporary_path, frontend_data_directory / report.filename)
            )
        for temporary_path, target in temporary_targets:
            os.replace(temporary_path, target)
        return tuple(str(target) for _, target in temporary_targets)
    finally:
        for temporary_path, _ in temporary_targets:
            temporary_path.unlink(missing_ok=True)


def build_player_insights_artifact(
    snapshot_path: str | Path,
    snapshot_sha256: str,
    artifact_directory: str | Path,
    *,
    builder: Callable = build_material_insights,
    specs: tuple[ProjectionSpec, ...] = PLAYER_INSIGHT_PROJECTIONS,
    progress: Callable | None = None,
    progress_interval: int = 100_000,
) -> PlayerInsightsArtifactReport:
    """Build one immutable shared artifact and deterministic projection set."""
    snapshot_path = Path(snapshot_path).resolve()
    artifact_directory = Path(artifact_directory).resolve()
    observed_snapshot_sha256 = _sha256(snapshot_path)
    if observed_snapshot_sha256 != snapshot_sha256.casefold():
        raise ValueError(
            "snapshot SHA-256 mismatch: "
            f"expected {snapshot_sha256.casefold()}, observed {observed_snapshot_sha256}"
        )
    if artifact_directory.exists():
        raise FileExistsError(artifact_directory)
    artifact_directory.mkdir(parents=True)

    database_path = artifact_directory / "player-insights.db"
    started = time.perf_counter()
    build_report = builder(
        snapshot_path,
        database_path,
        snapshot_sha256=observed_snapshot_sha256,
        progress=progress,
        progress_interval=progress_interval,
    )
    build_seconds = time.perf_counter() - started
    peak_rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    build_payload = (
        asdict(build_report)
        if is_dataclass(build_report)
        else dict(build_report)
    )
    dataset_version = build_payload["dataset_version"]

    database_uri = f"file:{database_path}?mode=ro&immutable=1"
    with sqlite3.connect(database_uri, uri=True) as connection:
        quick_check_rows = connection.execute("PRAGMA quick_check").fetchall()
        if quick_check_rows != [("ok",)]:
            raise ValueError(
                f"player-insights quick_check failed: {quick_check_rows[:10]}"
            )
        foreign_key_violations = sum(
            1 for _ in connection.execute("PRAGMA foreign_key_check")
        )
        stored_dataset_versions = connection.execute(
            "SELECT dataset_version FROM insight_builds"
        ).fetchall()
        if stored_dataset_versions != [(dataset_version,)]:
            raise ValueError(
                "player-insights build record does not match the builder report"
            )

    database_sha256 = _sha256(database_path)
    projections = stage_player_insight_projections(
        database_path,
        artifact_directory / "projections",
        specs=specs,
    )
    result_path = artifact_directory / "monthly-refresh-result.json"
    result_payload = {
        "snapshot": {
            "path": str(snapshot_path),
            "sha256": observed_snapshot_sha256,
            "bytes": snapshot_path.stat().st_size,
        },
        "database": {
            "path": str(database_path),
            "sha256": database_sha256,
            "bytes": database_path.stat().st_size,
            "quick_check": "ok",
            "foreign_key_violations": 0,
        },
        "build": {
            **build_payload,
            "build_seconds": build_seconds,
            "games_per_second": (
                build_payload.get("accepted_games", 0) / build_seconds
                if build_seconds
                else None
            ),
            "peak_rss_bytes": peak_rss_bytes,
        },
        "projections": [asdict(report) for report in projections],
    }
    _write_json_atomically(result_path, result_payload)
    return PlayerInsightsArtifactReport(
        artifact_directory=str(artifact_directory),
        database_path=str(database_path),
        database_sha256=database_sha256,
        database_bytes=database_path.stat().st_size,
        dataset_version=dataset_version,
        quick_check="ok",
        foreign_key_violations=0,
        build_seconds=build_seconds,
        projections=projections,
        result_path=str(result_path),
    )
