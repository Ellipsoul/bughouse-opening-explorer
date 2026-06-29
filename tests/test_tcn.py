"""Tests for the TCN decoder, including bughouse drops and promotions."""

import json
import pathlib

import pytest

from bughouse_explorer.tcn import decode_tcn

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "sample_tcn.json"
FILES = set("abcdefgh")
RANKS = set("12345678")
PIECES = set("qnrbkp")


def _valid_square(sq):
    return len(sq) == 2 and sq[0] in FILES and sq[1] in RANKS


def test_documented_vector():
    # From chess.com's own decode docs: 'Mc' -> g5-c1.
    assert decode_tcn("Mc") == [{"from": "g5", "to": "c1"}]


def test_empty_and_corners():
    assert decode_tcn("") == []
    # 'aa' -> square index 0 to 0 == a1-a1; useful as a boundary check.
    assert decode_tcn("aa") == [{"from": "a1", "to": "a1"}]


def test_odd_length_rejected():
    with pytest.raises(ValueError):
        decode_tcn("abc")


def test_real_games_decode_in_range():
    fixtures = json.loads(FIXTURES.read_text())
    assert fixtures, "expected sampled bughouse games as fixtures"

    seen_drop = False
    seen_promotion = False
    for game in fixtures:
        moves = decode_tcn(game["tcn"])
        # Plies are two chars each.
        assert len(moves) == len(game["tcn"]) // 2
        for move in moves:
            assert _valid_square(move["to"])
            if "drop" in move:
                seen_drop = True
                assert move["drop"] in PIECES
                assert "from" not in move
            else:
                assert _valid_square(move["from"])
            if "promotion" in move:
                seen_promotion = True
                assert move["promotion"] in PIECES

    # Real bughouse games are full of drops; at least one fixture must exercise the path.
    assert seen_drop, "no drop move found across fixtures"
