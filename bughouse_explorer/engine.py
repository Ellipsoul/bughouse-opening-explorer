"""A single-board move applier for bughouse games.

This is deliberately NOT a legality checker. chess.com already recorded legal games; our job
is only to *replay* their moves to recover the board position after each ply, so positions can
be keyed (by FEN) and merged across games in the opening explorer.

Bughouse specifics:
- A *drop* (``{"drop": "n", "to": "f6"}``) places a captured piece — from the partner board —
  onto a square. Drops can produce unusual piece counts (e.g. three knights); the board is just
  a square->piece map, so that is fine.
- There is no pocket; drops are simply piece placements.

Moves come from ``tcn.decode_tcn`` (the indexer decodes each game's ``tcn`` field): each ply is
``{"from","to"}`` (optionally with ``"promotion"``) or ``{"drop","to"}``.
"""

FILES = "abcdefgh"
RANKS = "12345678"

# Standard starting placement, rank 8 -> rank 1.
_START_RANKS = ["rnbqkbnr", "pppppppp", "", "", "", "", "PPPPPPPP", "RNBQKBNR"]


def _start_board():
    board = {}
    for r, row in enumerate(_START_RANKS):
        rank = 8 - r
        if not row:
            continue
        for f, piece in enumerate(row):
            board[FILES[f] + str(rank)] = piece
    return board


class Board:
    """Mutable single board. Apply moves; read a FEN-style position key after each."""

    def __init__(self):
        self.board = _start_board()
        self.white_to_move = True
        # Castling availability, cleared as kings/rooks move or rooks are captured at home.
        self.castling = {"K": True, "Q": True, "k": True, "q": True}
        self.ep = None  # en-passant target square, e.g. "e3", or None

    # -- move application ---------------------------------------------------

    def apply(self, move):
        """Apply one ply given as a decoded-tcn move dict."""
        if "drop" in move:
            self._apply_drop(move)
        else:
            self._apply_normal(move)
        self.white_to_move = not self.white_to_move

    def _apply_drop(self, move):
        piece = move["drop"].upper() if self.white_to_move else move["drop"].lower()
        self.board[move["to"]] = piece
        self.ep = None

    def _apply_normal(self, move):
        src, dst = move["from"], move["to"]
        piece = self.board.pop(src)
        is_pawn = piece in "Pp"
        new_ep = None

        # En passant: pawn moves diagonally onto an empty square -> remove the passed pawn.
        if is_pawn and src[0] != dst[0] and dst not in self.board and dst == self.ep:
            captured_sq = dst[0] + src[1]
            self.board.pop(captured_sq, None)

        # Castling: king steps two files -> move the matching rook too.
        if piece in "Kk" and abs(FILES.index(dst[0]) - FILES.index(src[0])) == 2:
            rank = src[1]
            if dst[0] == "g":      # king-side
                self.board[ "f" + rank] = self.board.pop("h" + rank)
            else:                   # queen-side, dst file == "c"
                self.board["d" + rank] = self.board.pop("a" + rank)

        # Double pawn push -> set the en-passant target square behind the pawn.
        if is_pawn and abs(int(dst[1]) - int(src[1])) == 2:
            mid_rank = (int(dst[1]) + int(src[1])) // 2
            new_ep = dst[0] + str(mid_rank)

        # Promotion.
        if "promotion" in move:
            promo = move["promotion"]
            piece = promo.upper() if self.white_to_move else promo.lower()

        self._update_castling_rights(src, dst)
        self.board[dst] = piece
        self.ep = new_ep

    def _update_castling_rights(self, src, dst):
        # King or rook leaving home, or a rook captured on its home square, clears rights.
        for sq in (src, dst):
            if sq == "e1":
                self.castling["K"] = self.castling["Q"] = False
            elif sq == "e8":
                self.castling["k"] = self.castling["q"] = False
            elif sq == "h1":
                self.castling["K"] = False
            elif sq == "a1":
                self.castling["Q"] = False
            elif sq == "h8":
                self.castling["k"] = False
            elif sq == "a8":
                self.castling["q"] = False

    # -- position key -------------------------------------------------------

    def placement(self):
        """The piece-placement field of a FEN (rank 8 -> rank 1)."""
        rows = []
        for rank in range(8, 0, -1):
            row, empty = "", 0
            for f in FILES:
                piece = self.board.get(f + str(rank))
                if piece is None:
                    empty += 1
                else:
                    if empty:
                        row += str(empty)
                        empty = 0
                    row += piece
            if empty:
                row += str(empty)
            rows.append(row)
        return "/".join(rows)

    def position_key(self):
        """FEN without move counters: placement, side, castling, ep — the graph key."""
        color = "w" if self.white_to_move else "b"
        rights = "".join(k for k in "KQkq" if self.castling[k]) or "-"
        ep = self.ep or "-"
        return f"{self.placement()} {color} {rights} {ep}"


START_FEN = Board().position_key()


# -- move labels (SAN + a unique move id) -----------------------------------
#
# Computed against the board *before* the move is applied (needed for capture detection and
# SAN disambiguation). move_id is a UCI-style string unique among a position's continuations;
# san is a best-effort label for display (no check/mate suffixes, which would need legality).

_KNIGHT = [(1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)]
_DIAG = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
_ORTHO = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def _sq(f, r):
    if 0 <= f < 8 and 0 <= r < 8:
        return FILES[f] + RANKS[r]
    return None


def _attackers(board, piece_char, dst):
    """Squares holding `piece_char` from which that piece type reaches `dst` (blockers respected)."""
    df, dr = FILES.index(dst[0]), RANKS.index(dst[1])
    ptype = piece_char.upper()
    found = []
    if ptype == "N":
        for ox, oy in _KNIGHT:
            s = _sq(df + ox, dr + oy)
            if s and board.get(s) == piece_char:
                found.append(s)
        return found
    rays = _DIAG if ptype == "B" else _ORTHO if ptype == "R" else _DIAG + _ORTHO
    for ox, oy in rays:
        f, r = df + ox, dr + oy
        while 0 <= f < 8 and 0 <= r < 8:
            s = FILES[f] + RANKS[r]
            occ = board.get(s)
            if occ is not None:
                if occ == piece_char and ptype in ("B", "R", "Q"):
                    found.append(s)
                break
            f += ox
            r += oy
    return found


def label(board_obj, move):
    """Return (move_id, san) for `move` against the pre-move Board `board_obj`."""
    if "drop" in move:
        letter = move["drop"].upper()
        san = f"{letter}@{move['to']}"
        return san, san

    board = board_obj.board
    src, dst = move["from"], move["to"]
    piece = board[src]
    ptype = piece.upper()
    promo = move.get("promotion")
    move_id = src + dst + (promo.lower() if promo else "")

    # Castling.
    if ptype == "K" and abs(FILES.index(dst[0]) - FILES.index(src[0])) == 2:
        return move_id, ("O-O" if dst[0] == "g" else "O-O-O")

    is_capture = dst in board or (ptype == "P" and src[0] != dst[0])

    if ptype == "P":
        san = (src[0] + "x" + dst) if is_capture else dst
        if promo:
            san += "=" + promo.upper()
        return move_id, san

    # Disambiguate among other same-type pieces that also reach dst.
    others = [s for s in _attackers(board, piece, dst) if s != src]
    disambig = ""
    if others:
        if all(s[0] != src[0] for s in others):
            disambig = src[0]
        elif all(s[1] != src[1] for s in others):
            disambig = src[1]
        else:
            disambig = src
    return move_id, f"{ptype}{disambig}{'x' if is_capture else ''}{dst}"
