from datetime import datetime, timezone

from bughouse_explorer.crawler.domain import (
    is_qualifying_observation,
    normalize_username,
    select_partner_year_sample,
)


def _games(count):
    return [
        {"uuid": f"game-{i:02d}", "end_time": 1_700_000_000 + i} for i in range(count)
    ]


def test_annual_partner_sampling_selects_exactly_one_board():
    selected = select_partner_year_sample(_games(100), "larso", 2026, 2)

    assert selected in _games(100)


def test_annual_sampling_is_stable_across_order_and_changes_with_policy_version():
    games = _games(20)
    first = select_partner_year_sample(games, "Larso", 2026, 2)
    resumed = select_partner_year_sample(list(reversed(games)), "larso", 2026, 2)
    next_version = select_partner_year_sample(games, "larso", 2026, 3)

    assert first == resumed
    assert first["uuid"] == "game-01"
    assert next_version["uuid"] == "game-11"


def test_eligibility_is_inclusive_and_uses_a_one_calendar_year_window():
    started = datetime(2026, 7, 31, 12, tzinfo=timezone.utc)
    cutoff = int(datetime(2025, 7, 31, 12, tzinfo=timezone.utc).timestamp())
    upper_bound = int(started.timestamp())

    assert is_qualifying_observation(2000, cutoff, started)
    assert is_qualifying_observation(2000, upper_bound, started)
    assert not is_qualifying_observation(1999, cutoff, started)
    assert not is_qualifying_observation(2200, cutoff - 1, started)
    assert not is_qualifying_observation(2200, upper_bound + 1, started)
    assert not is_qualifying_observation("unknown", cutoff, started)
    assert not is_qualifying_observation(2200, "unknown", started)
    assert normalize_username("  Emeraldddd ") == "emeraldddd"
