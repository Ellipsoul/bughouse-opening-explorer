from datetime import datetime, timezone

from bughouse_explorer.crawler.domain import (
    is_qualifying_observation,
    normalize_username,
    select_partner_samples,
)


def _games(count):
    return [
        {"uuid": f"game-{i:02d}", "end_time": 1_700_000_000 + i}
        for i in range(count)
    ]


def test_adaptive_partner_sampling_uses_the_configured_volume_bands():
    assert len(select_partner_samples(_games(4), "larso", 2026, 7, 1)) == 4
    assert len(select_partner_samples(_games(5), "larso", 2026, 7, 1)) == 2
    assert len(select_partner_samples(_games(20), "larso", 2026, 7, 1)) == 2
    assert len(select_partner_samples(_games(21), "larso", 2026, 7, 1)) == 1


def test_medium_month_sampling_is_stable_and_spans_both_chronological_halves():
    games = _games(10)
    first = select_partner_samples(games, "Larso", 2026, 7, 1)
    resumed = select_partner_samples(list(reversed(games)), "larso", 2026, 7, 1)

    assert first == resumed
    assert first[0] in games[:5]
    assert first[1] in games[5:]


def test_eligibility_is_inclusive_and_uses_a_two_calendar_year_window():
    started = datetime(2026, 7, 31, 12, tzinfo=timezone.utc)
    cutoff = int(datetime(2024, 7, 31, 12, tzinfo=timezone.utc).timestamp())

    assert is_qualifying_observation(1800, cutoff, started)
    assert not is_qualifying_observation(1799, cutoff, started)
    assert not is_qualifying_observation(2200, cutoff - 1, started)
    assert not is_qualifying_observation("unknown", cutoff, started)
    assert not is_qualifying_observation(2200, "unknown", started)
    assert normalize_username("  Emeraldddd ") == "emeraldddd"
