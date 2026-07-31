from bughouse_explorer.crawler.records import normalize_callback_game


def test_callback_record_normalizes_uuid_partner_and_timestamped_elos():
    payload = {
        "game": {
            "id": 178381671803,
            "uuid": "d90dc0b9-7fd3-11f1-ac4d-6cfe54652c60",
            "partnerGameId": "d90dc0b8-7fd3-11f1-ac4d-6cfe54652c60",
            "type": "bughouse",
            "moveList": "mC0K",
            "endTime": 1784068490,
            "pgnHeaders": {
                "White": "gena217",
                "Black": "eekarf",
                "WhiteElo": 2341,
                "BlackElo": 2574,
                "TimeControl": "120",
            },
        },
        "players": {
            "top": {"username": "eekarf", "color": "black", "rating": 2574},
            "bottom": {"username": "gena217", "color": "white", "rating": 2341},
        },
    }

    record = normalize_callback_game(payload)

    assert record["partner_reference"] == "d90dc0b8-7fd3-11f1-ac4d-6cfe54652c60"
    assert record["participants"] == {
        "white": {
            "username": "gena217",
            "rating": 2341,
            "result": None,
            "rating_source": "callback_pgn",
        },
        "black": {
            "username": "eekarf",
            "rating": 2574,
            "result": None,
            "rating_source": "callback_pgn",
        },
    }
