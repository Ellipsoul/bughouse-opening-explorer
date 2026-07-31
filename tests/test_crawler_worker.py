from datetime import datetime, timezone

from bughouse_explorer.crawler.http import CallbackNotFound, FetchResult
from bughouse_explorer.crawler.migrations import apply_migrations
from bughouse_explorer.crawler.store import CrawlerStore
from bughouse_explorer.crawler.worker import CrawlWorker


BOARD_A = "d90dc0b8-7fd3-11f1-ac4d-6cfe54652c60"
BOARD_B = "d90dc0b9-7fd3-11f1-ac4d-6cfe54652c60"


def _callback(uuid, numeric_id, partner, white, black):
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


class ChessComBoundary:
    def get_archives(self, username):
        return [(2026, 7)] if username == "larso" else []

    def get_month(self, username, year, month, **validators):
        return FetchResult(
            data={
                "games": [
                    {
                        "uuid": BOARD_A,
                        "url": "https://www.chess.com/game/live/178381671801",
                        "rules": "bughouse",
                        "end_time": 1784068490,
                        "tcn": "mC0K",
                        "white": {"username": "larso", "rating": 2200, "result": "win"},
                        "black": {"username": "ybothg", "rating": 2100, "result": "resigned"},
                    }
                ]
            },
            etag="tag",
            last_modified="today",
        )

    def get_callback(self, reference):
        if str(reference) == "178381671801":
            return _callback(BOARD_A, 178381671801, BOARD_B, "larso", "ybothg")
        if str(reference) == BOARD_B:
            return _callback(BOARD_B, 178381671803, BOARD_A, "gena217", "eekarf")
        raise AssertionError(f"unexpected callback reference: {reference}")


def test_worker_expands_from_seed_through_sampled_partner_board(tmp_path):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    store = CrawlerStore(path)
    store.seed_usernames(["larso"])
    worker = CrawlWorker(
        store,
        ChessComBoundary(),
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        sampler_version=1,
        worker_id="test-worker",
    )

    result = worker.run_until_idle()

    assert result["failed"] == 0
    assert store.status()["games"] == 2
    assert store.status()["partner_links"] == 2
    assert store.status()["players"]["eligible"] == 4
    assert store.status()["fully_crawled_players"] == 4


def test_worker_stops_at_a_total_fully_crawled_player_limit(tmp_path):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    store = CrawlerStore(path)
    store.seed_usernames(["larso"])
    worker = CrawlWorker(
        store,
        ChessComBoundary(),
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        worker_id="test-worker",
    )

    result = worker.run_until_idle(max_players=2)

    assert result["limit_reached"] is True
    assert store.status()["fully_crawled_players"] == 2
    assert store.status()["remaining_jobs"] > 0


def test_callback_404_gets_three_daily_retries_before_becoming_failed(tmp_path):
    path = str(tmp_path / "crawler.db")
    apply_migrations(path)
    now = [1_000]
    store = CrawlerStore(path, clock=lambda: now[0])
    store.save_public_month(
        "candidate",
        2026,
        7,
        [{
            "uuid": BOARD_A,
            "url": "https://www.chess.com/game/live/178381671801",
            "rules": "bughouse",
            "end_time": 1784068490,
            "white": {"username": "candidate", "rating": 1700, "result": "win"},
            "black": {"username": "other", "rating": 1700, "result": "loss"},
        }],
        run_started_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    class MissingCallback:
        def get_callback(self, reference):
            raise CallbackNotFound("not ready")

    worker = CrawlWorker(store, MissingCallback(), worker_id="test-worker")
    for attempt in range(4):
        result = worker.run_until_idle(max_jobs=1)
        if attempt < 3:
            assert result["deferred"] == 1
            assert store.status()["jobs"]["deferred"] == 1
            now[0] += 86_401

    assert result["failed"] == 1
    assert store.status()["jobs"]["failed"] == 1
