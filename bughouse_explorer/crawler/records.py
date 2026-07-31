"""Normalize Chess.com callback payloads into the crawler's canonical board shape."""

from __future__ import annotations


def _integer(value):
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _players_by_color(payload):
    result = {}
    for player in (payload.get("players") or {}).values():
        color = str(player.get("color") or "").lower()
        if color in ("white", "black"):
            result[color] = player
    return result


def _result_for(color, pgn_result):
    if pgn_result == "1-0":
        return "win" if color == "white" else "loss"
    if pgn_result == "0-1":
        return "win" if color == "black" else "loss"
    if pgn_result == "1/2-1/2":
        return "draw"
    return None


def normalize_callback_game(payload):
    """Validate and flatten one callback response without assuming partner-id type."""
    game = payload.get("game") or {}
    if game.get("type") != "bughouse" or not game.get("uuid"):
        raise ValueError("callback payload is not a Bughouse board")
    headers = game.get("pgnHeaders") or {}
    live_players = _players_by_color(payload)
    participants = {}
    for color, title in (("white", "White"), ("black", "Black")):
        live = live_players.get(color) or {}
        username = headers.get(title) or live.get("username")
        if not username:
            continue
        pgn_rating = _integer(headers.get(f"{title}Elo"))
        participants[color] = {
            "username": username,
            "rating": pgn_rating if pgn_rating is not None else _integer(live.get("rating")),
            "result": _result_for(color, headers.get("Result")),
            "rating_source": (
                "callback_pgn" if pgn_rating is not None else "callback_profile"
            ),
        }
    numeric_id = _integer(game.get("id"))
    return {
        "uuid": str(game["uuid"]),
        "numeric_id": numeric_id,
        "partner_reference": (
            str(game["partnerGameId"]) if game.get("partnerGameId") is not None else None
        ),
        "end_time": _integer(game.get("endTime")),
        "time_control": headers.get("TimeControl"),
        "time_class": None,
        "rated": game.get("isRated"),
        "rules": "bughouse",
        "tcn": game.get("moveList"),
        "initial_setup": game.get("initialSetup") or headers.get("FEN"),
        "fen": headers.get("FEN"),
        "url": (
            f"https://www.chess.com/game/live/{numeric_id}" if numeric_id is not None else None
        ),
        "participants": participants,
        "raw_payload": payload,
    }
