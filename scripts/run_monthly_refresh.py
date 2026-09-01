#!/usr/bin/env python3
"""Run the monthly crawler-to-Player-Insights refresh with explicit release gates."""

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

from bughouse_explorer.monthly_refresh import (
    build_player_insights_artifact,
    create_checked_crawler_snapshot,
    publish_staged_projections,
    summarize_crawler_database,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _default_period(now: datetime) -> tuple[int, int]:
    previous = now.replace(day=1) - timedelta(days=1)
    return previous.year, previous.month


def main() -> None:
    now = datetime.now(timezone.utc)
    default_year, default_month = _default_period(now)
    parser = argparse.ArgumentParser(
        description=(
            "Refresh Chess.com crawler data, create a checked immutable snapshot, "
            "rebuild every registered Player Insight, and optionally replace the "
            "checked frontend projections. This command never deploys."
        )
    )
    parser.add_argument(
        "--crawler-db",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "crawler.db",
    )
    parser.add_argument("--year", type=int, default=default_year)
    parser.add_argument(
        "--month", type=int, choices=range(1, 13), default=default_month
    )
    parser.add_argument(
        "--run-label",
        default=now.strftime("%Y%m%d"),
        help="immutable output label; use a new label for every retry",
    )
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument(
        "--skip-crawl",
        action="store_true",
        help="finalize an already completed monthly crawler run",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        help="bounded crawler smoke only; closure will prevent snapshotting",
    )
    parser.add_argument("--progress-interval", type=int, default=100_000)
    parser.add_argument("--frontend-data-dir", type=Path)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="atomically replace the validated local frontend projection set",
    )
    args = parser.parse_args()

    if args.progress_interval <= 0:
        parser.error("--progress-interval must be positive")
    if args.max_jobs is not None and args.max_jobs <= 0:
        parser.error("--max-jobs must be positive")
    if args.publish and args.frontend_data_dir is None:
        parser.error("--publish requires --frontend-data-dir")

    snapshot = args.snapshot or (
        REPOSITORY_ROOT
        / "snapshots"
        / f"monthly-{args.run_label}"
        / f"crawler-through-{args.year:04d}-{args.month:02d}.db"
    )
    artifact_directory = args.artifact_dir or (
        REPOSITORY_ROOT / "artifacts" / "insights" / f"monthly-{args.run_label}"
    )

    before_crawl = None
    if not args.skip_crawl:
        before_crawl = summarize_crawler_database(args.crawler_db)
        command = [
            sys.executable,
            "-m",
            "bughouse_explorer.cli",
            "crawl",
            "--crawler-db",
            str(args.crawler_db),
            "monthly",
            "--year",
            str(args.year),
            "--month",
            str(args.month),
        ]
        if args.max_jobs is not None:
            command.extend(("--max-jobs", str(args.max_jobs)))
        subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)

    after_crawl = summarize_crawler_database(args.crawler_db)
    deltas = None
    if before_crawl is not None:
        deltas = {
            key: getattr(after_crawl, key) - getattr(before_crawl, key)
            for key in (
                "games",
                "participants",
                "players",
                "permanently_tracked_players",
                "fully_crawled_players",
            )
        }
    snapshot_report = create_checked_crawler_snapshot(args.crawler_db, snapshot)
    snapshot_result = snapshot.resolve().parent / "snapshot-result.json"
    snapshot_result.write_text(
        json.dumps(
            {
                "period": f"{args.year:04d}-{args.month:02d}",
                "before_crawl": asdict(before_crawl) if before_crawl else None,
                "after_crawl": asdict(after_crawl),
                "deltas": deltas,
                "snapshot": asdict(snapshot_report),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    def report_progress(payload: dict) -> None:
        print(
            json.dumps({"event": "insights-progress", **payload}, sort_keys=True),
            file=sys.stderr,
            flush=True,
        )

    artifact_report = build_player_insights_artifact(
        snapshot,
        snapshot_report.snapshot_sha256,
        artifact_directory,
        progress=report_progress,
        progress_interval=args.progress_interval,
    )
    published = ()
    if args.publish:
        published = publish_staged_projections(
            Path(artifact_report.artifact_directory) / "projections",
            args.frontend_data_dir,
            artifact_report.projections,
        )

    workflow_payload = {
        "period": f"{args.year:04d}-{args.month:02d}",
        "before_crawl": asdict(before_crawl) if before_crawl else None,
        "after_crawl": asdict(after_crawl),
        "deltas": deltas,
        "snapshot": asdict(snapshot_report),
        "snapshot_result": str(snapshot_result),
        "player_insights": asdict(artifact_report),
        "published": list(published),
        "deployment_performed": False,
    }
    workflow_result = (
        Path(artifact_report.artifact_directory) / "monthly-workflow-result.json"
    )
    workflow_result.write_text(
        json.dumps(workflow_payload, indent=2, sort_keys=True) + "\n"
    )
    workflow_payload["workflow_result"] = str(workflow_result)
    print(json.dumps(workflow_payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
