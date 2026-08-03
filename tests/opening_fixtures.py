from bughouse_explorer.opening.adapter import OpeningGame
from bughouse_explorer.tcn import _T


def token(source, target):
    def index(square):
        return (int(square[1]) - 1) * 8 + ord(square[0]) - ord("a")

    return _T[index(source)] + _T[index(target)]


E4 = token("e2", "e4")
E5 = token("e7", "e5")
NF3 = token("g1", "f3")
C5 = token("c7", "c5")
D4 = token("d2", "d4")
D5 = token("d7", "d5")
A6 = token("a7", "a6")
DROP_Q_E2 = "&" + _T[(2 - 1) * 8 + 4]


def game(uuid, moves, white=None, black=None):
    return OpeningGame(
        uuid=uuid,
        move_tokens=tuple(moves),
        white_username=white or f"white-{uuid}",
        black_username=black or f"black-{uuid}",
        white_rating=2000,
        black_rating=2000,
        white_result="win",
        black_result="checkmated",
        end_time=1_700_000_000,
        time_control="180",
        rated=True,
        url=f"https://example.invalid/{uuid}",
        source="public",
        content_hash=f"hash-{uuid}",
    )


def corpus():
    return [
        game("a", (E4, E5), "alice", "xavier"),
        game("b", (E4, E5), "alice", "yara"),
        game("c", (E4, E5, NF3), "carol", "xavier"),
        game("d", (E4, C5, NF3), "alice", "xavier"),
        game("e", (D4, D5), "erin", "zane"),
        game("f", (E4, A6, DROP_Q_E2), "fran", "zed"),
        game("g", (E4, A6, DROP_Q_E2, E5), "gabe", "zed"),
    ]
