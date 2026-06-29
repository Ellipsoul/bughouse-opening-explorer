"""Decode chess.com's TCN move encoding.

Bughouse games on chess.com carry no PGN; their moves live in the ``tcn`` field, a
compact two-characters-per-ply encoding. This is a direct port of chess.com's own
``decodeTCN`` routine, including the bughouse drop and promotion cases.

Each ply is two characters indexing the 64-symbol alphabet ``_T``:

* first char ``a`` -> origin. ``a`` in 0..63 is a board square; ``a`` >= 79 is a
  *drop*, where the dropped piece is ``"qnrbkp"[a - 79]`` and there is no origin square.
* second char ``b`` -> destination square (0..63). ``b`` > 63 marks a *promotion*; the
  promotion piece is ``"qnrbkp"[(b - 64) // 3]`` and the true destination is recovered
  by stepping one rank from the origin.

A square index ``s`` maps to ``file = "abcdefgh"[s % 8]`` and ``rank = s // 8 + 1``,
so 0 -> "a1" and 63 -> "h8".
"""

_T = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!?{~}(^)[_]@#$,./&-*++="
_PIECES = "qnrbkp"


def _square(index):
    return _T[index % 8] + str(index // 8 + 1)


def decode_tcn(tcn):
    """Decode a TCN string into a list of move dicts.

    Each move has a ``to`` square and either a ``from`` square (normal move) or a
    ``drop`` piece (bughouse drop). Promotions additionally carry a ``promotion`` piece.
    """
    moves = []
    if not tcn:
        return moves
    if len(tcn) % 2 != 0:
        raise ValueError(f"TCN length must be even, got {len(tcn)}")

    for i in range(0, len(tcn), 2):
        a = _T.index(tcn[i])
        b = _T.index(tcn[i + 1])
        move = {}

        if b > 63:
            move["promotion"] = _PIECES[(b - 64) // 3]
            b = a + (-8 if a < 16 else 8) + ((b - 64) % 3) - 1

        if a > 75:
            move["drop"] = _PIECES[a - 79]
        else:
            move["from"] = _square(a)

        move["to"] = _square(b)
        moves.append(move)

    return moves
