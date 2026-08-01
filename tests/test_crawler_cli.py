from datetime import datetime, timedelta, timezone

from click.testing import CliRunner

from bughouse_explorer.cli import main
from bughouse_explorer.crawler.migrations import apply_migrations, connect
from bughouse_explorer.crawler.store import CrawlerStore


def test_cli_exposes_crawler_and_reference_commands_without_legacy_fetching():
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0, result.output
    assert "crawl" in result.output
    assert "index" in result.output
    assert "serve" in result.output
    assert "download" not in result.output
    assert "update" not in result.output


def test_crawl_migrate_and_seed_commands_initialize_the_sqlite_queue(tmp_path):
    path = str(tmp_path / "crawler.db")
    runner = CliRunner()

    migrated = runner.invoke(main, ["crawl", "--crawler-db", path, "migrate"])
    assert migrated.exit_code == 0, migrated.output

    seeded = runner.invoke(
        main, ["crawl", "--crawler-db", path, "seed", "Larso", "LARSO"]
    )
    assert seeded.exit_code == 0, seeded.output

    conn = connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM crawl_jobs").fetchone()[0] == 1
    finally:
        conn.close()


def test_rebuild_probes_uses_the_existing_runs_eligibility_cutoff(tmp_path):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    store = CrawlerStore(path)
    run_id = store.start_run("bootstrap", {"sampler_version": 1})
    store.finish_run(run_id, "stopped")

    result = CliRunner().invoke(
        main,
        [
            "crawl",
            "--crawler-db",
            path,
            "rebuild-probes",
            run_id,
            "--sampler-version",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Rebuilt partner probes for sampler version 2" in result.output
    assert '"removed_jobs": 0' in result.output


def test_reconcile_command_restores_stranded_player_work(tmp_path):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    store = CrawlerStore(path)
    now = datetime.now(timezone.utc)
    store.save_public_month(
        "larso",
        now.year,
        now.month,
        [{
            "uuid": "00000000-0000-0000-0000-000000000052",
            "url": "https://www.chess.com/game/live/123456789052",
            "rules": "bughouse",
            "end_time": int(now.timestamp()),
            "white": {"username": "larso", "rating": 2000, "result": "win"},
            "black": {"username": "other", "rating": 1500, "result": "loss"},
        }],
        run_started_at=now,
    )
    archive = store.lease_job("setup-worker")
    store.complete_job(archive.id, {"months": 1})
    run_id = store.start_run("bootstrap")
    store.finish_run(run_id, "stopped")

    result = CliRunner().invoke(
        main, ["crawl", "--crawler-db", path, "reconcile", run_id]
    )

    assert result.exit_code == 0, result.output
    assert '"requeued_archive_lists": 1' in result.output


def test_bounded_bootstrap_requeues_the_current_partial_month(tmp_path):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    store = CrawlerStore(path)
    now = datetime.now(timezone.utc)
    store.save_public_month(
        "larso",
        now.year,
        now.month,
        [
            {
                "uuid": "00000000-0000-0000-0000-000000000030",
                "url": "https://www.chess.com/game/live/123456789030",
                "rules": "bughouse",
                "end_time": int(now.timestamp()),
                "white": {"username": "larso", "rating": 2000, "result": "win"},
                "black": {"username": "other", "rating": 1700, "result": "loss"},
            }
        ],
        run_started_at=now,
        etag="partial-current-month",
    )
    assert store.mark_full_crawl_completed_if_done("larso")

    result = CliRunner().invoke(
        main,
        [
            "crawl",
            "--crawler-db",
            path,
            "bootstrap",
            "--max-players",
            "1",
            "--no-seed-initial",
        ],
    )

    assert result.exit_code == 0, result.output
    assert '"limit_reached": true' in result.output
    assert store.month_cache("larso", now.year, now.month)["status"] == "queued"


def test_resume_prints_live_job_progress(tmp_path, monkeypatch):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    CrawlerStore(path).seed_usernames(["larso"])

    class ChessComBoundary:
        def __init__(self, **_kwargs):
            pass

        def get_archives(self, username):
            assert username == "larso"
            return []

    monkeypatch.setattr(
        "bughouse_explorer.crawler.cli.ChessComCrawlerClient",
        ChessComBoundary,
    )

    result = CliRunner().invoke(
        main,
        ["crawl", "--crawler-db", path, "resume", "--max-jobs", "1"],
    )

    assert result.exit_code == 0, result.output
    assert " START archive_list#" in result.output
    assert "username=larso mode=qualify" in result.output
    assert " DONE archive_list#" in result.output
    assert "months=0" in result.output
    assert "HTTP: 0 retries, 0 rate limits (429), 0 recoveries" in result.output


def test_resume_discards_legacy_work_before_bughouse_existed(tmp_path, monkeypatch):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    store = CrawlerStore(path)
    store.seed_usernames(["larso"])
    conn = store._connection()
    try:
        with conn:
            player_id = conn.execute(
                "SELECT id FROM players WHERE username = 'larso'"
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO player_months (player_id, year, month, status) "
                "VALUES (?, 2015, 12, 'queued')",
                (player_id,),
            )
            conn.execute(
                """
                INSERT INTO crawl_jobs
                    (job_key, type, payload, status, attempts, max_attempts,
                     available_at, created_at, updated_at)
                VALUES
                    ('month:larso:2015-12', 'month',
                     '{"username":"larso","year":2015,"month":12,"mode":"full"}',
                     'queued', 0, 5, 0, 0, 0)
                """
            )
    finally:
        conn.close()

    class ChessComBoundary:
        def __init__(self, **_kwargs):
            pass

        def get_archives(self, username):
            return []

        def get_month(self, *_args, **_kwargs):
            raise AssertionError("pre-2016 month must not be fetched")

    monkeypatch.setattr(
        "bughouse_explorer.crawler.cli.ChessComCrawlerClient",
        ChessComBoundary,
    )

    result = CliRunner().invoke(
        main,
        ["crawl", "--crawler-db", path, "resume", "--max-jobs", "1"],
    )

    assert result.exit_code == 0, result.output
    assert "Discarded 1 unfinished pre-2016 month job(s)" in result.output
    assert "DONE archive_list#" in result.output


def test_http_rate_limits_are_printed_and_persisted(tmp_path, monkeypatch):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    CrawlerStore(path).seed_usernames(["larso"])

    class ChessComBoundary:
        def __init__(self, *, observer, **_kwargs):
            self.observer = observer

        def get_archives(self, _username):
            self.observer(
                {
                    "event": "http_retry",
                    "url": "https://api.chess.com/pub/player/larso/games/archives",
                    "status": 429,
                    "attempt": 1,
                    "elapsed_ms": 125,
                    "retry_in_seconds": 10,
                    "retry_after": "10",
                }
            )
            self.observer(
                {
                    "event": "http_recovered",
                    "url": "https://api.chess.com/pub/player/larso/games/archives",
                    "status": 200,
                    "attempts": 2,
                    "elapsed_ms": 80,
                    "total_elapsed_ms": 10_205,
                }
            )
            return []

    monkeypatch.setattr(
        "bughouse_explorer.crawler.cli.ChessComCrawlerClient",
        ChessComBoundary,
    )

    result = CliRunner().invoke(
        main,
        ["crawl", "--crawler-db", path, "resume", "--max-jobs", "1"],
    )

    assert result.exit_code == 0, result.output
    assert "HTTP RETRY status=429 attempt=1 retry_in=10s" in result.output
    assert "HTTP RECOVERED status=200 attempts=2" in result.output
    assert "HTTP: 1 retries, 1 rate limits (429), 1 recoveries" in result.output
    counters = CrawlerStore(path).status()["run"]["counters"]
    assert counters["http_429s"] == 1
    assert counters["http_retries"] == 1
    assert counters["http_recoveries"] == 1


def test_resume_applies_the_current_eligibility_policy_before_work(tmp_path):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    store = CrawlerStore(path)
    now = datetime.now(timezone.utc)
    store.save_public_month(
        "larso",
        now.year,
        now.month,
        [
            {
                "uuid": "00000000-0000-0000-0000-000000000050",
                "url": "https://www.chess.com/game/live/123456789050",
                "rules": "bughouse",
                "end_time": int(now.timestamp()),
                "white": {"username": "larso", "rating": 2000, "result": "win"},
                "black": {"username": "other", "rating": 1500, "result": "loss"},
            }
        ],
        run_started_at=now,
    )
    conn = store._connection()
    try:
        with conn:
            conn.execute(
                "UPDATE game_participants SET rating = 1999 "
                "WHERE player_id = (SELECT id FROM players WHERE username = 'larso')"
            )
    finally:
        conn.close()

    result = CliRunner().invoke(
        main,
        ["crawl", "--crawler-db", path, "resume", "--max-jobs", "0"],
    )

    assert result.exit_code == 0, result.output
    assert "Marked 1 player(s) dormant under the current eligibility policy" in result.output
    assert store.status()["players"]["dormant"] == 1


def test_explicit_resume_keeps_the_original_runs_eligibility_cutoff(tmp_path):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    store = CrawlerStore(path)
    now = datetime.now(timezone.utc)
    original_start = now - timedelta(days=30)
    observation = now.replace(year=now.year - 1) - timedelta(days=15)
    store.save_public_month(
        "larso",
        observation.year,
        observation.month,
        [{
            "uuid": "00000000-0000-0000-0000-000000000051",
            "url": "https://www.chess.com/game/live/123456789051",
            "rules": "bughouse",
            "end_time": int(observation.timestamp()),
            "white": {"username": "larso", "rating": 2000, "result": "win"},
            "black": {"username": "other", "rating": 1500, "result": "loss"},
        }],
        run_started_at=original_start,
    )
    run_id = store.start_run("bootstrap")
    conn = store._connection()
    try:
        with conn:
            conn.execute(
                "UPDATE crawl_runs SET started_at = ?, status = 'stopped' WHERE id = ?",
                (int(original_start.timestamp()), run_id),
            )
    finally:
        conn.close()

    result = CliRunner().invoke(
        main,
        ["crawl", "--crawler-db", path, "resume", run_id, "--max-jobs", "0"],
    )

    assert result.exit_code == 0, result.output
    assert store.status()["players"]["eligible"] == 1
    assert store.status()["players"]["dormant"] == 0


def test_idle_run_with_failed_work_is_not_reported_complete(tmp_path):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    store = CrawlerStore(path)
    store.seed_usernames(["larso"])
    job = store.lease_job("setup-worker")
    store.fail_job(job.id, "unexpected schema change")
    run_id = store.start_run("bootstrap")
    store.finish_run(run_id, "stopped")

    result = CliRunner().invoke(
        main,
        ["crawl", "--crawler-db", path, "resume", run_id, "--max-jobs", "0"],
    )

    assert result.exit_code == 0, result.output
    assert store.get_run(run_id)["status"] == "stopped"
