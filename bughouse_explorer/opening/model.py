"""Public query records shared by opening-index representations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Branch:
    move_token: str
    support: int
    results: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class QueryFilter:
    white_username: str | None = None
    black_username: str | None = None

    def __post_init__(self):
        if self.white_username is not None:
            object.__setattr__(self, "white_username", self.white_username.strip().casefold())
        if self.black_username is not None:
            object.__setattr__(self, "black_username", self.black_username.strip().casefold())


@dataclass(frozen=True)
class NodeView:
    prefix: tuple[str, ...]
    position_fen: str
    support: int
    branches: tuple[Branch, ...]
    ended_game_uuids: tuple[str, ...]
    sole_game_uuid: str | None


class PrefixNotFound(KeyError):
    """The requested exact move prefix is absent from the materialized trie."""


def replay_prefix(prefix: tuple[str, ...]) -> str:
    """Project an exact move prefix to a display FEN; never use it as identity."""
    from bughouse_explorer.engine import Board
    from bughouse_explorer.tcn import decode_tcn

    board = Board()
    for move in decode_tcn("".join(prefix)):
        board.apply(move)
    return board.position_key()
