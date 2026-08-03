from bughouse_explorer.opening.model import QueryFilter
from bughouse_explorer.opening.relational import RelationalIndex, build_relational_index
from opening_fixtures import A6, C5, DROP_Q_E2, E4, E5, NF3, corpus, game, token


def test_relational_index_retains_duplicate_and_internal_game_endings(tmp_path):
    artifact = tmp_path / "opening.sqlite3"
    build_relational_index(corpus(), artifact, source_fingerprint="fixture-v1")

    with RelationalIndex(artifact) as index:
        node = index.query((E4, E5))

    assert node.support == 3
    assert node.ended_game_uuids == ("a", "b")
    assert [(branch.move_token, branch.support) for branch in node.branches] == [
        (NF3, 1)
    ]
    assert node.sole_game_uuid is None


def test_relational_filters_are_seat_specific_and_can_terminate_early(tmp_path):
    artifact = tmp_path / "opening.sqlite3"
    build_relational_index(corpus(), artifact, source_fingerprint="fixture-v1")

    with RelationalIndex(artifact) as index:
        white = index.query((), QueryFilter(white_username="carol"))
        black = index.query((), QueryFilter(black_username="yara"))
        pairing = index.query(
            (E4,), QueryFilter(white_username="alice", black_username="xavier")
        )

    assert (white.support, white.sole_game_uuid, white.branches) == (1, "c", ())
    assert (black.support, black.sole_game_uuid, black.branches) == (1, "b", ())
    assert pairing.support == 2
    assert [(branch.move_token, branch.support) for branch in pairing.branches] == [
        (E5, 1),
        (C5, 1),
    ]


def test_relational_drop_edge_is_navigable_and_prefix_is_replayed_for_display(tmp_path):
    artifact = tmp_path / "opening.sqlite3"
    build_relational_index(corpus(), artifact, source_fingerprint="fixture-v1")

    with RelationalIndex(artifact) as index:
        before_drop = index.query((E4, A6))
        after_drop = index.query((E4, A6, DROP_Q_E2))

    assert [(branch.move_token, branch.support) for branch in before_drop.branches] == [
        (DROP_Q_E2, 2)
    ]
    assert after_drop.position_fen.split(" ")[0].endswith("/PPPPQPPP/RNBQKBNR")


def test_equal_display_positions_from_different_move_orders_remain_separate_paths(tmp_path):
    knight_line = (
        token("g1", "f3"),
        token("g8", "f6"),
        token("f3", "g1"),
        token("f6", "g8"),
    )
    queen_knight_line = (
        token("b1", "c3"),
        token("b8", "c6"),
        token("c3", "b1"),
        token("c6", "b8"),
    )
    games = [
        game("n1", knight_line),
        game("n2", knight_line),
        game("q1", queen_knight_line),
        game("q2", queen_knight_line),
    ]
    artifact = tmp_path / "opening.sqlite3"
    build_relational_index(games, artifact, source_fingerprint="transpositions")

    with RelationalIndex(artifact) as index:
        first = index.query(knight_line)
        second = index.query(queen_knight_line)

    assert first.prefix != second.prefix
    assert first.position_fen == second.position_fen
    assert first.support == second.support == 2
