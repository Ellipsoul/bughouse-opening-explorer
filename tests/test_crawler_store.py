from datetime import datetime, timezone

import pytest

from bughouse_explorer.crawler.migrations import apply_migrations
from bughouse_explorer.crawler.store import CrawlerStore


@pytest.fixture()
def store(tmp_path):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    return CrawlerStore(path)


def test_seed_players_are_idempotent_and_make_durable_archive_jobs(store):
    store.seed_usernames([" Larso ", "larso", "Emeraldddd"])
    store.seed_usernames(["LARSO"])

    status = store.status()
    assert status["players"] == {"candidate": 2, "eligible": 0, "dormant": 0}
    assert status["jobs"]["queued"] == 2

    leased = store.lease_job("test-worker")
    assert leased.type == "archive_list"
    assert leased.payload["username"] in {"larso", "emeraldddd"}


def test_public_month_ingestion_filters_bughouse_and_promotes_qualifying_players(store):
    recent = int(datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp())
    games = [
        {
            "uuid": "d90dc0b8-7fd3-11f1-ac4d-6cfe54652c60",
            "url": "https://www.chess.com/game/live/178381671801",
            "rules": "bughouse",
            "end_time": recent,
            "tcn": "mC0K",
            "white": {"username": "Larso", "rating": 1900, "result": "win"},
            "black": {"username": "Opponent", "rating": 1799, "result": "resigned"},
        },
        {
            "uuid": "00000000-0000-0000-0000-000000000001",
            "rules": "chess",
            "end_time": recent,
            "white": {"username": "Larso", "rating": 2500, "result": "win"},
            "black": {"username": "Other", "rating": 2500, "result": "resigned"},
        },
    ]

    summary = store.save_public_month(
        "larso",
        2026,
        7,
        games,
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        etag="month-tag",
        last_modified="today",
        sampler_version=1,
    )

    assert summary == {"archive_games": 2, "bughouse_games": 1, "probes": 1}
    assert store.status()["players"] == {"candidate": 1, "eligible": 1, "dormant": 0}
    stored = store.get_game("d90dc0b8-7fd3-11f1-ac4d-6cfe54652c60")
    assert stored["numeric_id"] == 178381671801
    assert stored["participants"] == {
        "white": {"username": "larso", "rating": 1900, "result": "win"},
        "black": {"username": "opponent", "rating": 1799, "result": "resigned"},
    }


def test_callback_boards_link_bidirectionally_and_discover_partner_players(store):
    first_uuid = "d90dc0b8-7fd3-11f1-ac4d-6cfe54652c60"
    second_uuid = "d90dc0b9-7fd3-11f1-ac4d-6cfe54652c60"

    def payload(uuid, numeric_id, partner, white, black):
        return {
            "game": {
                "id": numeric_id,
                "uuid": uuid,
                "partnerGameId": partner,
                "type": "bughouse",
                "moveList": "mC0K",
                "endTime": 1784068490,
                "pgnHeaders": {
                    "White": white,
                    "Black": black,
                    "WhiteElo": 2200,
                    "BlackElo": 2100,
                    "TimeControl": "120",
                },
            },
            "players": {},
        }

    started = datetime(2026, 7, 31, tzinfo=timezone.utc)
    store.save_callback_game(
        payload(first_uuid, 178381671801, second_uuid, "larso", "ybothg"),
        run_started_at=started,
    )
    store.save_callback_game(
        payload(second_uuid, 178381671803, first_uuid, "gena217", "eekarf"),
        run_started_at=started,
    )

    assert store.status()["partner_links"] == 2
    assert store.get_game(first_uuid)["partner_uuid"] == second_uuid
    assert store.get_game(second_uuid)["partner_uuid"] == first_uuid
    assert store.status()["players"]["eligible"] == 4


def test_expired_job_lease_is_recovered_after_an_interruption(tmp_path):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    now = [1_000]
    store = CrawlerStore(path, clock=lambda: now[0])
    store.seed_usernames(["larso"])

    first = store.lease_job("worker-one", lease_seconds=10)
    assert first.attempts == 1

    now[0] = 1_011
    recovered = store.lease_job("worker-two", lease_seconds=10)
    assert recovered.id == first.id
    assert recovered.attempts == 2


def test_repeated_expired_leases_never_exhaust_the_retry_budget(tmp_path):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    now = [1_000]
    store = CrawlerStore(path, clock=lambda: now[0])
    store.seed_usernames(["larso"])

    for expected_attempt in range(1, 6):
        leased = store.lease_job("worker", lease_seconds=1)
        assert leased.attempts == expected_attempt
        now[0] += 2

    recovered = store.lease_job("worker", lease_seconds=1)

    assert recovered.id == leased.id
    assert recovered.attempts == 1
    assert store.status()["jobs"]["failed"] == 0


def test_eligibility_can_become_dormant_and_reactivate_on_a_later_game(store):
    def game(uuid, numeric_id, end_time, rating):
        return {
            "uuid": uuid,
            "url": f"https://www.chess.com/game/live/{numeric_id}",
            "rules": "bughouse",
            "end_time": end_time,
            "white": {"username": "larso", "rating": rating, "result": "win"},
            "black": {"username": "other", "rating": 1500, "result": "resigned"},
        }

    original_time = int(datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp())
    store.save_public_month(
        "larso",
        2026,
        7,
        [
            game(
                "00000000-0000-0000-0000-000000000010",
                123456789010,
                original_time,
                1900,
            )
        ],
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )
    assert store.status()["players"]["eligible"] == 1

    store.reevaluate_dormancy(datetime(2028, 8, 1, tzinfo=timezone.utc))
    assert store.status()["players"]["dormant"] == 1

    later_time = int(datetime(2028, 7, 20, tzinfo=timezone.utc).timestamp())
    store.save_public_month(
        "larso",
        2028,
        7,
        [game("00000000-0000-0000-0000-000000000011", 123456789011, later_time, 1900)],
        run_started_at=datetime(2028, 8, 1, tzinfo=timezone.utc),
    )
    assert store.status()["players"]["eligible"] == 1
    conn = store._connection()
    try:
        reactivation = conn.execute(
            "SELECT type, payload FROM crawl_jobs "
            "WHERE job_key LIKE 'reactivate:archive:larso:%'"
        ).fetchone()
    finally:
        conn.close()
    assert reactivation is not None
    assert reactivation["type"] == "archive_list"


def test_monthly_refresh_queues_only_active_eligible_players(store):
    end_time = int(datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp())
    store.save_public_month(
        "larso",
        2026,
        7,
        [
            {
                "uuid": "00000000-0000-0000-0000-000000000020",
                "url": "https://www.chess.com/game/live/123456789020",
                "rules": "bughouse",
                "end_time": end_time,
                "white": {"username": "larso", "rating": 2000, "result": "win"},
                "black": {
                    "username": "candidate",
                    "rating": 1700,
                    "result": "resigned",
                },
            }
        ],
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    assert store.queue_monthly_refresh(2026, 8) == ["larso"]


def test_monthly_refresh_reactivates_a_completed_job_for_the_same_month(store):
    end_time = int(datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp())
    store.save_public_month(
        "larso",
        2026,
        7,
        [
            {
                "uuid": "00000000-0000-0000-0000-000000000021",
                "url": "https://www.chess.com/game/live/123456789021",
                "rules": "bughouse",
                "end_time": end_time,
                "white": {"username": "larso", "rating": 2000, "result": "win"},
                "black": {
                    "username": "candidate",
                    "rating": 1700,
                    "result": "resigned",
                },
            }
        ],
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )
    store.queue_monthly_refresh(2026, 8)

    conn = store._connection()
    try:
        with conn:
            conn.execute(
                "UPDATE crawl_jobs SET status = 'complete', attempts = 4 "
                "WHERE job_key = 'refresh:2026-08:larso'"
            )
    finally:
        conn.close()

    store.queue_monthly_refresh(2026, 8)

    conn = store._connection()
    try:
        job = conn.execute(
            "SELECT status, attempts FROM crawl_jobs "
            "WHERE job_key = 'refresh:2026-08:larso'"
        ).fetchone()
    finally:
        conn.close()
    assert dict(job) == {"status": "queued", "attempts": 0}


def test_month_job_attempt_and_failure_are_visible_in_player_month(store):
    store.seed_usernames(["larso"])
    archive = store.lease_job("worker")
    store.complete_job(archive.id)
    store.schedule_archive_months(
        "larso",
        [(2026, 7)],
        mode="qualify",
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    month = store.lease_job("worker")
    store.defer_job(month.id, "try later", delay_seconds=60)

    assert store.month_cache("larso", 2026, 7) == {
        "etag": None,
        "last_modified": None,
        "status": "deferred",
        "attempts": 1,
        "last_error": "try later",
    }


def test_resuming_a_run_returns_its_original_start_time(tmp_path):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    now = [1_000]
    store = CrawlerStore(path, clock=lambda: now[0])
    run_id = store.start_run("bootstrap")
    store.finish_run(run_id, "stopped")
    now[0] = 2_000

    run = store.resume_run(run_id)

    assert run["started_at"] == 1_000
    assert run["heartbeat_at"] == 2_000


def test_malformed_bughouse_records_do_not_abort_an_archive_month(store):
    summary = store.save_public_month(
        "larso",
        2026,
        7,
        [{"rules": "bughouse", "end_time": 1784068490}],
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    assert summary == {
        "archive_games": 1,
        "bughouse_games": 0,
        "probes": 0,
        "malformed_games": 1,
    }
    assert store.month_cache("larso", 2026, 7)["status"] == "complete"


def test_transient_job_remains_deferred_after_each_retry_budget(store):
    store.seed_usernames(["larso"])

    for _ in range(5):
        job = store.lease_job("worker")
        outcome = store.defer_job(
            job.id,
            "temporary outage",
            delay_seconds=0,
            preserve_after_exhaustion=True,
        )

    assert outcome == "deferred"
    assert store.status()["jobs"]["deferred"] == 1

    conn = store._connection()
    try:
        attempts = conn.execute(
            "SELECT attempts FROM crawl_jobs WHERE id = ?", (job.id,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert attempts == 5
