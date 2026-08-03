from bughouse_explorer.opening.adapter import OpeningGame
from bughouse_explorer.opening.shape import measure_sorted_token_lines, measure_trie_shape


def _game(uuid, moves):
    return OpeningGame(
        uuid=uuid,
        move_tokens=tuple(moves),
        white_username=f"white-{uuid}",
        black_username=f"black-{uuid}",
        white_rating=2000,
        black_rating=2000,
        white_result="win",
        black_result="checkmated",
        end_time=1_700_000_000,
        time_control="180",
        rated=True,
        url=None,
        source="public",
        content_hash=f"hash-{uuid}",
    )


def test_shape_uses_exact_prefixes_and_counts_duplicate_and_internal_endings():
    games = [
        _game("a", ("mC", "0K")),
        _game("b", ("mC", "0K")),
        _game("c", ("mC", "0K", "gv")),
        _game("d", ("mC", "cM", "bs")),
        _game("e", ("bs", "mC")),
    ]

    shape = measure_trie_shape(games)

    assert shape.games == 5
    assert shape.nodes_by_ply == {0: 1, 1: 2, 2: 2, 3: 1}
    assert shape.terminal_depths == {1: 1, 2: 3, 3: 1}
    assert shape.identical_complete_line_groups == 1
    assert shape.games_in_identical_complete_lines == 2
    assert shape.games_ending_at_internal_nodes == 2
    assert shape.membership_entries == 15
    assert shape.interval_nodes == 6


def test_streaming_sorted_shape_matches_in_memory_reference():
    games = [
        _game("a", ("mC", "0K")),
        _game("b", ("mC", "0K")),
        _game("c", ("mC", "0K", "gv")),
        _game("d", ("mC", "cM", "bs")),
        _game("e", ("bs", "mC")),
    ]
    sorted_lines = sorted(
        ((game.move_tokens, game.uuid) for game in games),
        key=lambda item: item,
    )

    assert measure_sorted_token_lines(sorted_lines) == measure_trie_shape(games)
