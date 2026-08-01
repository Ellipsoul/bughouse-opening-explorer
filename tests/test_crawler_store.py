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


def test_closure_audit_rejects_unreconciled_failed_jobs(store):
    store.seed_usernames(["larso"])
    job = store.lease_job("test-worker")
    store.fail_job(job.id, "unexpected schema change")

    audit = store.closure_audit()

    assert audit["ready"] is False
    assert audit["failed_jobs"] == 1


def test_reconciliation_requeues_an_eligible_player_with_no_completion_path(store):
    started = datetime(2026, 7, 31, tzinfo=timezone.utc)
    store.save_public_month(
        "larso",
        2026,
        7,
        [{
            "uuid": "00000000-0000-0000-0000-000000000099",
            "url": "https://www.chess.com/game/live/123456789099",
            "rules": "bughouse",
            "end_time": int(datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp()),
            "white": {"username": "larso", "rating": 2000, "result": "win"},
            "black": {"username": "other", "rating": 1500, "result": "loss"},
        }],
        run_started_at=started,
    )
    old_archive = store.lease_job("setup-worker")
    store.complete_job(old_archive.id, {"months": 1})

    result = store.reconcile_crawl_state()

    assert result["requeued_archive_lists"] == 1
    job = store.lease_job("test-worker")
    assert job.type == "archive_list"
    assert job.payload == {"username": "larso", "mode": "full"}


def test_reconciliation_converts_existing_public_month_404_to_terminal(store):
    started = datetime(2026, 7, 31, tzinfo=timezone.utc)
    store.save_public_month(
        "larso",
        2026,
        7,
        [{
            "uuid": "00000000-0000-0000-0000-000000000098",
            "url": "https://www.chess.com/game/live/123456789098",
            "rules": "bughouse",
            "end_time": int(datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp()),
            "white": {"username": "larso", "rating": 2000, "result": "win"},
            "black": {"username": "other", "rating": 1500, "result": "loss"},
        }],
        run_started_at=started,
    )
    archive = store.lease_job("setup-worker")
    store.schedule_archive_months(
        "larso", [(2018, 3), (2026, 7)], mode="full", run_started_at=started
    )
    store.complete_job(archive.id, {"months": 2})
    month = store.lease_job("setup-worker")
    store.fail_job(month.id, "HTTP 404: missing historical month")

    result = store.reconcile_crawl_state()

    assert result["terminalized_months"] == 1
    assert store.status()["jobs"]["failed"] == 0
    assert store.status()["terminal"]["unavailable_months"] == 1
    assert store.status()["latest_error"] is None


def test_refetched_archive_list_requeues_a_missing_month_with_an_old_completed_job(store):
    started = datetime(2026, 7, 31, tzinfo=timezone.utc)
    store.schedule_archive_months(
        "larso", [(2018, 3)], mode="full", run_started_at=started
    )
    old_job = store.lease_job("setup-worker")
    store.complete_job(old_job.id)
    conn = store._connection()
    try:
        with conn:
            conn.execute(
                "DELETE FROM player_months WHERE player_id = "
                "(SELECT id FROM players WHERE username = 'larso')"
            )
    finally:
        conn.close()

    store.schedule_archive_months(
        "larso", [(2018, 3)], mode="full", run_started_at=started
    )

    recovered = store.lease_job("test-worker")
    assert recovered is not None
    assert recovered.type == "month"
    assert recovered.payload["mode"] == "full"


def test_public_month_ingestion_filters_bughouse_and_promotes_qualifying_players(store):
    recent = int(datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp())
    games = [
        {
            "uuid": "d90dc0b8-7fd3-11f1-ac4d-6cfe54652c60",
            "url": "https://www.chess.com/game/live/178381671801",
            "rules": "bughouse",
            "end_time": recent,
            "tcn": "mC0K",
            "white": {"username": "Larso", "rating": 2000, "result": "win"},
            "black": {"username": "Opponent", "rating": 1999, "result": "resigned"},
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

    assert summary == {"archive_games": 2, "bughouse_games": 1, "probes": 0}
    assert store.status()["players"] == {"candidate": 1, "eligible": 1, "dormant": 0}
    stored = store.get_game("d90dc0b8-7fd3-11f1-ac4d-6cfe54652c60")
    assert stored["numeric_id"] == 178381671801
    assert stored["participants"] == {
        "white": {"username": "larso", "rating": 2000, "result": "win"},
        "black": {"username": "opponent", "rating": 1999, "result": "resigned"},
    }


def test_same_public_board_reached_through_both_players_is_stored_once(store):
    game = {
        "uuid": "00000000-0000-0000-0000-000000000002",
        "url": "https://www.chess.com/game/live/123456789002",
        "rules": "bughouse",
        "end_time": int(datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp()),
        "white": {"username": "larso", "rating": 2000, "result": "win"},
        "black": {"username": "opponent", "rating": 1950, "result": "resigned"},
    }
    started = datetime(2026, 7, 31, tzinfo=timezone.utc)

    store.save_public_month(
        "larso", 2026, 7, [game], run_started_at=started
    )
    store.save_public_month(
        "opponent", 2026, 7, [game], run_started_at=started
    )

    assert store.status()["games"] == 1
    assert store.get_game(game["uuid"])["participants"] == {
        "white": {"username": "larso", "rating": 2000, "result": "win"},
        "black": {"username": "opponent", "rating": 1950, "result": "resigned"},
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
                2000,
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
        [game("00000000-0000-0000-0000-000000000011", 123456789011, later_time, 2000)],
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


def test_policy_reevaluation_applies_the_current_rating_threshold(store):
    observed_at = int(datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp())
    store.save_public_month(
        "larso",
        2026,
        7,
        [
            {
                "uuid": "00000000-0000-0000-0000-000000000012",
                "url": "https://www.chess.com/game/live/123456789012",
                "rules": "bughouse",
                "end_time": observed_at,
                "white": {"username": "larso", "rating": 2000, "result": "win"},
                "black": {"username": "other", "rating": 1500, "result": "loss"},
            }
        ],
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )
    conn = store._connection()
    try:
        with conn:
            conn.execute(
                "UPDATE game_participants SET rating = 1999 "
                "WHERE player_id = (SELECT id FROM players WHERE username = 'larso')"
            )
            conn.execute(
                "UPDATE players SET qualifying_rating = 1999 "
                "WHERE username = 'larso'"
            )
    finally:
        conn.close()

    dormant = store.reevaluate_dormancy(
        datetime(2026, 7, 31, tzinfo=timezone.utc)
    )

    assert dormant == 1
    assert store.status()["players"]["dormant"] == 1
    assert store.lease_job("worker") is None


def test_policy_reevaluation_ignores_callback_profile_ratings(store):
    old_observation = int(datetime(2024, 7, 20, tzinfo=timezone.utc).timestamp())
    store.save_public_month(
        "larso",
        2024,
        7,
        [
            {
                "uuid": "00000000-0000-0000-0000-000000000013",
                "url": "https://www.chess.com/game/live/123456789013",
                "rules": "bughouse",
                "end_time": old_observation,
                "white": {"username": "larso", "rating": 2000, "result": "win"},
                "black": {"username": "other", "rating": 1500, "result": "loss"},
            }
        ],
        run_started_at=datetime(2024, 7, 31, tzinfo=timezone.utc),
    )
    store.save_callback_game(
        {
            "game": {
                "type": "bughouse",
                "uuid": "00000000-0000-0000-0000-000000000014",
                "id": 123456789014,
                "endTime": int(
                    datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp()
                ),
                "pgnHeaders": {"White": "larso", "Result": "1-0"},
            },
            "players": {
                "white": {
                    "color": "white",
                    "username": "larso",
                    "rating": 2300,
                }
            },
        },
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    dormant = store.reevaluate_dormancy(
        datetime(2026, 7, 31, tzinfo=timezone.utc)
    )

    assert dormant == 1
    assert store.status()["players"]["dormant"] == 1


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

    assert store.queue_monthly_refresh(2015, 12) == []
    assert store.month_cache("larso", 2015, 12) is None
    assert store.queue_monthly_refresh(2026, 8) == ["larso"]


def test_monthly_refresh_does_not_requeue_a_terminal_unavailable_month(store):
    end_time = int(datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp())
    store.save_public_month(
        "larso",
        2026,
        7,
        [{
            "uuid": "00000000-0000-0000-0000-000000000025",
            "url": "https://www.chess.com/game/live/123456789025",
            "rules": "bughouse",
            "end_time": end_time,
            "white": {"username": "larso", "rating": 2000, "result": "win"},
            "black": {"username": "other", "rating": 1500, "result": "loss"},
        }],
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )
    store.queue_monthly_refresh(2026, 8)
    refresh = store.lease_job("test-worker")
    assert refresh.payload["mode"] == "monthly"
    store.mark_month_terminal_unavailable(refresh.id, "HTTP 404: unavailable")

    queued = store.queue_monthly_refresh(2026, 8)

    assert queued == []
    assert store.lease_job("test-worker").type == "archive_list"


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


def test_current_month_is_queued_again_after_a_partial_archive_fetch(store):
    end_time = int(datetime(2026, 7, 30, tzinfo=timezone.utc).timestamp())
    store.save_public_month(
        "larso",
        2026,
        7,
        [
            {
                "uuid": "00000000-0000-0000-0000-000000000022",
                "url": "https://www.chess.com/game/live/123456789022",
                "rules": "bughouse",
                "end_time": end_time,
                "white": {"username": "larso", "rating": 2000, "result": "win"},
                "black": {"username": "candidate", "rating": 1700, "result": "loss"},
            }
        ],
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        etag="partial-month",
    )
    assert store.month_cache("larso", 2026, 7)["status"] == "complete"

    queued = store.queue_current_month_refresh(
        datetime(2026, 7, 31, tzinfo=timezone.utc)
    )

    assert queued == ["larso"]
    assert store.month_cache("larso", 2026, 7)["status"] == "queued"


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


def test_lifetime_month_work_is_leased_before_broader_discovery(store):
    store.seed_usernames(["older-seed"])
    end_time = int(datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp())
    store.save_public_month(
        "larso",
        2026,
        7,
        [
            {
                "uuid": "00000000-0000-0000-0000-000000000040",
                "url": "https://www.chess.com/game/live/123456789040",
                "rules": "bughouse",
                "end_time": end_time,
                "white": {"username": "larso", "rating": 2000, "result": "win"},
                "black": {"username": "other", "rating": 1700, "result": "loss"},
            }
        ],
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )
    store.schedule_archive_months(
        "larso",
        [(2020, 1)],
        mode="full",
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    job = store.lease_job("worker")

    assert job.type == "month"
    assert job.payload == {
        "username": "larso",
        "year": 2020,
        "month": 1,
        "mode": "full",
    }


def test_archive_scheduling_starts_with_january_2016(store):
    selected = store.schedule_archive_months(
        "larso",
        [(2015, 12), (2016, 1), (2016, 2)],
        mode="full",
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    assert selected == [(2016, 1), (2016, 2)]
    assert store.status()["jobs"]["queued"] == 2


def test_seed_qualification_scans_only_the_latest_calendar_year(store):
    selected = store.schedule_archive_months(
        "larso",
        [(2025, 6), (2025, 7), (2026, 1), (2026, 7)],
        mode="qualify",
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    assert selected == [(2026, 7), (2026, 1), (2025, 7)]


def test_pre_2016_work_from_an_existing_queue_is_discarded(store):
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

    discarded = store.discard_pre_bughouse_month_work()

    assert discarded == {"jobs": 1, "player_months": 1}
    assert store.month_cache("larso", 2015, 12) is None
    assert store.lease_job("worker").type == "archive_list"


def test_probe_queue_rebuild_keeps_one_recent_sample_per_eligible_player_year(store):
    started = datetime(2026, 7, 31, tzinfo=timezone.utc)
    observations = [
        (2024, 8, 1, "00000000-0000-0000-0000-000000000101"),
        (2025, 7, 31, "00000000-0000-0000-0000-000000000102"),
        (2025, 12, 1, "00000000-0000-0000-0000-000000000103"),
        (2026, 7, 1, "00000000-0000-0000-0000-000000000104"),
    ]
    for year, month, day, board_uuid in observations:
        store.save_public_month(
            "larso",
            year,
            month,
            [
                {
                    "uuid": board_uuid,
                    "url": f"https://www.chess.com/game/live/{year}{month:02d}{day:02d}",
                    "rules": "bughouse",
                    "end_time": int(
                        datetime(year, month, day, tzinfo=timezone.utc).timestamp()
                    ),
                    "white": {
                        "username": "larso",
                        "rating": 2000,
                        "result": "win",
                    },
                    "black": {
                        "username": f"opponent-{year}-{month}",
                        "rating": 1800,
                        "result": "loss",
                    },
                }
            ],
            run_started_at=started,
            sampler_version=1,
        )

    assert store.mark_full_crawl_completed_if_done("larso")
    archive = store.lease_job("worker")
    assert archive.type == "archive_list"
    store.complete_job(archive.id)
    conn = store._connection()
    try:
        with conn:
            now = int(started.timestamp())
            for index, (_, _, _, board_uuid) in enumerate(observations):
                conn.execute(
                    """
                    INSERT INTO crawl_jobs
                        (job_key, type, payload, status, attempts, max_attempts,
                         available_at, created_at, updated_at)
                    VALUES (?, 'partner_probe', ?, 'queued', 0, 4, ?, ?, ?)
                    """,
                    (
                        f"partner:{board_uuid}",
                        '{"board_uuid":"' + board_uuid
                        + '","reference":"legacy","sampler_version":1}',
                        now + index,
                        now,
                        now,
                    ),
                )
    finally:
        conn.close()

    rebuilt = store.rebuild_partner_probe_queue(
        run_started_at=started,
        sampler_version=2,
    )

    assert rebuilt == {
        "removed_jobs": 4,
        "eligible_players": 1,
        "samples": 2,
        "queued_jobs": 2,
        "reused_jobs": 0,
    }
    probes = [store.lease_job("worker"), store.lease_job("worker")]
    assert {probe.payload["year"] for probe in probes} == {2025, 2026}
    assert {probe.payload["sampler_version"] for probe in probes} == {2}
    assert all(probe.type == "partner_probe" for probe in probes)
    assert store.lease_job("worker") is None


def test_current_year_partner_sample_is_frozen_after_later_games_arrive(store):
    started = datetime(2026, 7, 31, tzinfo=timezone.utc)

    def ingest(board_uuid, day):
        store.save_public_month(
            "larso",
            2026,
            7,
            [
                {
                    "uuid": board_uuid,
                    "url": f"https://www.chess.com/game/live/123456789{day:03d}",
                    "rules": "bughouse",
                    "end_time": int(
                        datetime(2026, 7, day, tzinfo=timezone.utc).timestamp()
                    ),
                    "white": {
                        "username": "larso",
                        "rating": 2000,
                        "result": "win",
                    },
                    "black": {
                        "username": "other",
                        "rating": 1800,
                        "result": "loss",
                    },
                }
            ],
            run_started_at=started,
        )

    ingest("frozen-old", 1)
    assert store.mark_full_crawl_completed_if_done("larso")
    archive = store.lease_job("worker")
    assert archive.type == "archive_list"
    store.complete_job(archive.id)

    first = store.schedule_partner_year_probes(
        "larso", run_started_at=started, sampler_version=2
    )
    assert first == {"samples": 1, "queued_jobs": 1, "reused_jobs": 0}
    probe = store.lease_job("worker")
    assert probe.payload["board_uuid"] == "frozen-old"
    store.complete_job(probe.id)

    ingest("new-0", 2)
    second = store.schedule_partner_year_probes(
        "larso", run_started_at=started, sampler_version=2
    )

    assert second == {"samples": 0, "queued_jobs": 0, "reused_jobs": 1}
    assert store.lease_job("worker") is None


def test_annual_samples_share_one_globally_deduplicated_probe_job(store):
    started = datetime(2026, 7, 31, tzinfo=timezone.utc)
    store.save_public_month(
        "larso",
        2026,
        7,
        [
            {
                "uuid": "shared-board",
                "url": "https://www.chess.com/game/live/123456789999",
                "rules": "bughouse",
                "end_time": int(
                    datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp()
                ),
                "white": {"username": "larso", "rating": 2000, "result": "win"},
                "black": {"username": "ybothg", "rating": 2100, "result": "loss"},
            }
        ],
        run_started_at=started,
    )
    assert store.mark_full_crawl_completed_if_done("larso")
    assert store.mark_full_crawl_completed_if_done("ybothg")
    for _ in range(2):
        archive = store.lease_job("worker")
        assert archive.type == "archive_list"
        store.complete_job(archive.id)

    rebuilt = store.rebuild_partner_probe_queue(
        run_started_at=started, sampler_version=2
    )

    assert rebuilt["samples"] == 2
    assert rebuilt["queued_jobs"] == 1
    assert rebuilt["reused_jobs"] == 1
    assert store.lease_job("worker").payload["board_uuid"] == "shared-board"
    assert store.lease_job("worker") is None


def test_probe_queue_rebuild_preserves_completed_probe_audit_records(store):
    conn = store._connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO crawl_jobs
                    (job_key, type, payload, status, attempts, max_attempts,
                     available_at, created_at, updated_at)
                VALUES ('partner:completed', 'partner_probe',
                        '{"board_uuid":"completed","sampler_version":1}',
                        'queued', 0, 4, 0, 0, 0)
                """
            )
    finally:
        conn.close()
    completed = store.lease_job("worker")
    store.complete_job(completed.id)

    rebuilt = store.rebuild_partner_probe_queue(
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        sampler_version=2,
    )

    assert rebuilt["removed_jobs"] == 0
    assert store.status()["jobs"]["complete"] == 1


def test_probe_queue_rebuild_refuses_to_delete_a_leased_probe(store):
    conn = store._connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO crawl_jobs
                    (job_key, type, payload, status, attempts, max_attempts,
                     available_at, created_at, updated_at)
                VALUES ('partner:leased', 'partner_probe',
                        '{"board_uuid":"leased","sampler_version":1}',
                        'queued', 0, 4, 0, 0, 0)
                """
            )
    finally:
        conn.close()
    assert store.lease_job("worker").type == "partner_probe"

    with pytest.raises(RuntimeError, match="probe job is leased"):
        store.rebuild_partner_probe_queue(
            run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
            sampler_version=2,
        )

    assert store.status()["jobs"]["leased"] == 1
