"""Engine tests. The headline test replays real games and checks the final placement."""

import json
import pathlib

from bughouse_explorer.engine import Board, START_FEN, label

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "sample_games.json"


def _replay(moves):
    b = Board()
    for m in moves:
        b.apply(m)
    return b


def test_real_games_reproduce_final_placement():
    """Replaying each game's moves must yield the position chess.com recorded as final."""
    games = json.loads(FIXTURES.read_text())
    assert games
    for g in games:
        b = _replay(g["moves"])
        expected_placement = g["fen"].split(" ")[0]
        assert b.placement() == expected_placement, g["uuid"]


def test_start_fen():
    assert START_FEN == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"


def test_kingside_castle_moves_rook():
    b = Board()
    for m in [{"from": "e2", "to": "e4"}, {"from": "e7", "to": "e5"},
              {"from": "g1", "to": "f3"}, {"from": "b8", "to": "c6"},
              {"from": "f1", "to": "c4"}, {"from": "f8", "to": "c5"},
              {"from": "e1", "to": "g1"}]:  # white O-O
        b.apply(m)
    assert b.board.get("g1") == "K" and b.board.get("f1") == "R"
    assert b.board.get("h1") is None and b.board.get("e1") is None
    assert b.castling["K"] is False and b.castling["Q"] is False


def test_en_passant_removes_pawn():
    b = Board()
    for m in [{"from": "e2", "to": "e4"}, {"from": "a7", "to": "a6"},
              {"from": "e4", "to": "e5"}, {"from": "d7", "to": "d5"}]:
        b.apply(m)
    assert b.ep == "d6"
    b.apply({"from": "e5", "to": "d6"})  # exd6 e.p.
    assert b.board.get("d6") == "P" and b.board.get("d5") is None


def test_promotion():
    b = Board()
    b.board = {"a7": "P", "h1": "K", "h8": "k"}
    b.apply({"from": "a7", "to": "a8", "promotion": "q"})
    assert b.board.get("a8") == "Q"


def test_drop_places_piece():
    b = Board()
    mid, san = label(b, {"drop": "n", "to": "f6"})
    b.apply({"drop": "n", "to": "f6"})
    assert b.board.get("f6") == "N"  # white to move -> white knight
    assert san == "N@f6"


def test_san_labels():
    b = Board()
    assert label(b, {"from": "g1", "to": "f3"})[1] == "Nf3"
    assert label(b, {"from": "e2", "to": "e4"})[1] == "e4"
    # knight disambiguation by file
    b.board = {"b1": "N", "d1": "N", "e1": "K", "e8": "k"}
    assert label(b, {"from": "b1", "to": "c3"})[1] == "Nbc3"
