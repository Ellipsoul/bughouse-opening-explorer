from dataclasses import replace
import json

import pytest

from bughouse_explorer.opening.model import QueryFilter
from bughouse_explorer.opening.position_graph_packed import (
    EDGE_V2,
    PackedPositionGraph,
    POSITION_V2,
    STATE_V2,
    build_packed_position_graph,
)
from bughouse_explorer.opening.position_graph_v2 import repack_position_graph_v2
from bughouse_explorer.opening.publication import validate_artifact
from opening_fixtures import D4, E4, NF3, game, token


NF6 = token("g8", "f6")
NC3 = token("b1", "c3")
NC6 = token("b8", "c6")


def _games():
    first_order = (NF3, NF6, NC3, NC6)
    second_order = (NC3, NC6, NF3, NF6)
    return [
        replace(
            game("a", first_order + (E4,), white="Alice", black="Xavier"),
            uuid="00000000-0000-4000-8000-00000000000a",
            url="https://www.chess.com/game/live/1001",
        ),
        replace(
            game("b", second_order + (E4,), white="Alice", black="Yara"),
            uuid="00000000-0000-4000-8000-00000000000b",
            url="https://www.chess.com/game/live/1002",
            source="callback",
            provenance_flags=("callback_source",),
        ),
        replace(
            game("c", second_order + (D4,), white="Carol", black="Xavier"),
            uuid="00000000-0000-4000-8000-00000000000c",
            url="https://www.chess.com/game/live/1003",
        ),
    ]


def test_v1_repack_is_query_equivalent_and_keeps_only_browser_game_metadata(tmp_path):
    source = tmp_path / "v1"
    output = tmp_path / "v2"
    games = _games()
    build_packed_position_graph(games, source, source_fingerprint="v2-fixture")

    repack_position_graph_v2(source, output)

    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["format_version"] == "packed-position-graph-v2"
    with PackedPositionGraph(source) as v1, PackedPositionGraph(output) as v2:
        for state_id in range(v1.manifest["states"]):
            for query_filter in (
                None,
                QueryFilter(white_username="alice"),
                QueryFilter(black_username="xavier"),
            ):
                assert v2.query_state(state_id, query_filter) == v1.query_state(
                    state_id, query_filter
                )

        assert v2.game(1) == {
            "black_rating": 2000,
            "black_result": "checkmated",
            "black_username": "Yara",
            "provenance_flags": ["callback_source"],
            "source": "callback",
            "url": "https://www.chess.com/game/live/1002",
            "uuid": "00000000-0000-4000-8000-00000000000b",
            "white_rating": 2000,
            "white_result": "win",
            "white_username": "Alice",
        }


def test_v2_reuses_equal_position_state_and_incoming_edge_memberships(tmp_path):
    source = tmp_path / "v1"
    output = tmp_path / "v2"
    only_game = replace(
        game("a", (E4,)),
        uuid="00000000-0000-4000-8000-00000000000a",
        url="https://www.chess.com/game/live/1001",
    )
    build_packed_position_graph(
        [only_game], source, source_fingerprint="membership-sharing-fixture"
    )

    repack_position_graph_v2(source, output)

    positions = list(POSITION_V2.iter_unpack((output / "positions.bin").read_bytes()))
    states = list(STATE_V2.iter_unpack((output / "states.bin").read_bytes()))
    edges = list(EDGE_V2.iter_unpack((output / "edges.bin").read_bytes()))
    assert states[0][3:5] == positions[states[0][0]][2:4]
    assert states[1][3:5] == positions[states[1][0]][2:4]
    assert edges[0][4:6] == states[edges[0][0]][3:5]
    assert (output / "memberships.bin").stat().st_size == 3 * 4


def test_v2_passes_the_publication_boundary(tmp_path):
    source = tmp_path / "v1"
    output = tmp_path / "v2"
    build_packed_position_graph(_games(), source, source_fingerprint="publish-v2")
    repack_position_graph_v2(source, output)

    published = validate_artifact(output)

    assert published.format == "packed-position-graph"
    assert published.build_id == json.loads((source / "manifest.json").read_text())[
        "build_id"
    ]


def test_repack_rejects_a_corrupted_v1_source_before_writing_a_v2_manifest(tmp_path):
    source = tmp_path / "v1"
    output = tmp_path / "v2"
    build_packed_position_graph(_games(), source, source_fingerprint="corrupt-v1")
    with (source / "strings.bin").open("ab") as stream:
        stream.write(b"corruption")

    with pytest.raises(ValueError, match="source (size|hash) mismatch: strings.bin"):
        repack_position_graph_v2(source, output)

    assert not (output / "manifest.json").exists()


def test_v2_repack_is_component_deterministic(tmp_path):
    source = tmp_path / "v1"
    first = tmp_path / "v2-first"
    second = tmp_path / "v2-second"
    build_packed_position_graph(_games(), source, source_fingerprint="stable-v2")

    repack_position_graph_v2(source, first)
    repack_position_graph_v2(source, second)

    assert {
        path.name: path.read_bytes() for path in first.iterdir() if path.is_file()
    } == {
        path.name: path.read_bytes() for path in second.iterdir() if path.is_file()
    }


def test_v2_repack_rejects_non_chess_com_game_urls(tmp_path):
    source = tmp_path / "v1"
    output = tmp_path / "v2"
    invalid = replace(_games()[0], url="https://example.invalid/game/1001")
    build_packed_position_graph(
        [invalid], source, source_fingerprint="non-chess-com-v2"
    )

    with pytest.raises(ValueError, match="unsupported non-Chess.com game URL"):
        repack_position_graph_v2(source, output)

    assert not (output / "manifest.json").exists()


def test_v2_does_not_share_a_single_cycle_edge_with_the_implicit_root_entry(tmp_path):
    source = tmp_path / "v1"
    output = tmp_path / "v2"
    cycle = (NF3, NF6, token("f3", "g1"), token("f6", "g8"))
    games = [
        replace(
            game("first", (E4,)),
            uuid="00000000-0000-4000-8000-000000000001",
            url="https://www.chess.com/game/live/1001",
        ),
        replace(
            game("cycle", cycle),
            uuid="00000000-0000-4000-8000-000000000002",
            url="https://www.chess.com/game/live/1002",
        ),
    ]
    build_packed_position_graph(games, source, source_fingerprint="root-cycle-v2")
    repack_position_graph_v2(source, output)

    with PackedPositionGraph(output) as graph:
        returning_edge = next(
            edge_id
            for edge_id in range(graph.manifest["edges"])
            if graph._edge(edge_id)[1] == graph.root_state_id
        )

        assert graph.matching_state_games(graph.root_state_id) == (0, 1)
        assert graph.matching_edge_games(returning_edge) == (1,)
