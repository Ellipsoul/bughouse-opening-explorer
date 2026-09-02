from bughouse_explorer.opening.position_graph import build_position_graph
from opening_fixtures import D4, E4, NF3, game, token


NF6 = token("g8", "f6")
NC3 = token("b1", "c3")
NC6 = token("b8", "c6")
NG1 = token("f3", "g1")
NG8 = token("f6", "g8")
RG1 = token("h1", "g1")
RH1 = token("g1", "h1")


def test_move_order_transpositions_share_one_position_and_continuations():
    first_order = (NF3, NF6, NC3, NC6)
    second_order = (NC3, NC6, NF3, NF6)
    graph = build_position_graph(
        [
            game("a", first_order + (E4,)),
            game("b", second_order + (E4,)),
            game("c", second_order + (D4,)),
        ],
        source_fingerprint="transposition-fixture",
    )

    first = graph.trace(first_order)
    second = graph.trace(second_order)

    assert first.position_id == second.position_id
    assert first.state_id == second.state_id

    view = graph.query_state(first.state_id)
    assert view.position_support == 3
    assert view.state_support == 3
    assert [(branch.move_token, branch.support) for branch in view.branches] == [
        (E4, 2),
        (D4, 1),
    ]


def test_revisiting_a_position_does_not_double_count_a_game():
    loop = (NF3, NF6, NG1, NG8)
    graph = build_position_graph(
        [game("loop", loop + loop + (E4,))],
        source_fingerprint="cycle-fixture",
    )

    root = graph.trace(())
    revisited = graph.trace(loop)

    assert root.position_id == revisited.position_id
    assert root.state_id == revisited.state_id
    assert graph.query_state(root.state_id).state_support == 1
    assert [(branch.move_token, branch.support) for branch in graph.query_state(root.state_id).branches] == [
        (NF3, 1),
        (E4, 1),
    ]


def test_rule_state_is_occurrence_context_not_position_identity():
    loses_white_kingside_castling = (
        NF3,
        NF6,
        RG1,
        NG8,
        RH1,
        NF6,
        NG1,
        NG8,
    )
    graph = build_position_graph(
        [game("rights", loses_white_kingside_castling + (E4,))],
        source_fingerprint="rule-state-fixture",
    )

    initial = graph.trace(())
    returned = graph.trace(loses_white_kingside_castling)

    assert initial.position_id == returned.position_id
    assert initial.state_id != returned.state_id
    assert initial.position_fen.endswith(" w KQkq -")
    assert returned.position_fen.endswith(" w Qkq -")
    assert [branch.move_token for branch in graph.query_state(returned.state_id).branches] == [E4]
