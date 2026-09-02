"""Reference position graph used to specify transposition-aware semantics.

The production builder is deliberately allowed to use a different, bounded-memory
representation.  This module is the small-corpus oracle: it makes the identities and
counting rules explicit enough that packed/streaming implementations can be compared
against it byte-for-byte at their public query boundary.

Identity has two layers:

* a position is only the piece-placement field of FEN;
* a state is a position plus side-to-move, castling rights, and en-passant target.

The second layer belongs to a navigation occurrence, not to node identity.  It is
required to decide which outgoing move tokens are legal and how to replay them after
different histories transpose onto the same placement.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib

from bughouse_explorer.engine import Board, label
from bughouse_explorer.tcn import decode_tcn

from .adapter import OpeningGame
from .model import QueryFilter


DRAW_RESULTS = frozenset(
    {
        "50move",
        "agreed",
        "insufficient",
        "repetition",
        "stalemate",
        "timevsinsufficient",
        "timevsinsufficientmaterial",
    }
)


def result_bucket(game: OpeningGame) -> str:
    """Collapse raw Chess.com result strings to the explorer's three outcomes."""
    if game.white_result == "win":
        return "win"
    if game.white_result in DRAW_RESULTS or game.black_result in DRAW_RESULTS:
        return "draw"
    return "loss"


@dataclass(frozen=True)
class GraphPosition:
    id: int
    placement: str


@dataclass(frozen=True)
class GraphState:
    id: int
    position_id: int
    position_fen: str


@dataclass(frozen=True)
class GraphEdge:
    id: int
    parent_state_id: int
    child_position_id: int
    child_state_id: int
    move_token: str
    move_label: str


@dataclass(frozen=True)
class GraphOccurrence:
    position_id: int
    state_id: int
    position_fen: str


@dataclass(frozen=True)
class GraphBranch:
    edge_id: int
    child_position_id: int
    child_state_id: int
    move_token: str
    move_label: str
    support: int
    results: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class GraphStateView:
    position_id: int
    state_id: int
    position_fen: str
    position_support: int
    state_support: int
    actual_ending_count: int
    branches: tuple[GraphBranch, ...]
    sole_game_uuid: str | None


class GraphInvariantError(ValueError):
    """The replayed corpus violates a deterministic graph identity invariant."""


def identity_key(domain: str, value: str | bytes) -> bytes:
    """Return the stable 160-bit ordering/identity key used by every builder."""
    payload = value.encode() if isinstance(value, str) else value
    digest = hashlib.blake2b(digest_size=20, person=b"opening-graph-v1")
    digest.update(domain.encode())
    digest.update(b"\0")
    digest.update(payload)
    return digest.digest()


class PositionGraph:
    """Immutable in-memory oracle for a transposition-aware opening graph."""

    def __init__(
        self,
        *,
        build_id: str,
        games: tuple[OpeningGame, ...],
        positions: tuple[GraphPosition, ...],
        states: tuple[GraphState, ...],
        edges: tuple[GraphEdge, ...],
        position_games: tuple[frozenset[int], ...],
        state_games: tuple[frozenset[int], ...],
        edge_games: tuple[frozenset[int], ...],
        ending_games: tuple[frozenset[int], ...],
        root_state_id: int,
    ):
        self.build_id = build_id
        self.games = games
        self.positions = positions
        self.states = states
        self.edges = edges
        self.position_games = position_games
        self.state_games = state_games
        self.edge_games = edge_games
        self.ending_games = ending_games
        self.root_state_id = root_state_id
        self.root_position_id = states[root_state_id].position_id
        self._edge_by_parent_token = {
            (edge.parent_state_id, edge.move_token): edge for edge in edges
        }
        outgoing = defaultdict(list)
        for edge in edges:
            outgoing[edge.parent_state_id].append(edge)
        self._outgoing = {
            state_id: tuple(values) for state_id, values in outgoing.items()
        }

    def trace(self, move_tokens: tuple[str, ...]) -> GraphOccurrence:
        """Follow an exact history through state-qualified edges.

        This helper exists for tests and diagnostics.  Production navigation keeps
        the state id returned on each edge and does not ask the server to rediscover
        ancestry for a multi-parent node.
        """
        state_id = self.root_state_id
        for move_token in move_tokens:
            try:
                state_id = self._edge_by_parent_token[(state_id, move_token)].child_state_id
            except KeyError as error:
                raise KeyError((state_id, move_token)) from error
        state = self.states[state_id]
        return GraphOccurrence(state.position_id, state.id, state.position_fen)

    def _selected_games(self, query_filter: QueryFilter | None) -> frozenset[int] | None:
        if query_filter is None:
            return None
        selected = []
        for ordinal, game in enumerate(self.games):
            if (
                query_filter.white_username is not None
                and game.white_username.casefold() != query_filter.white_username
            ):
                continue
            if (
                query_filter.black_username is not None
                and game.black_username.casefold() != query_filter.black_username
            ):
                continue
            selected.append(ordinal)
        return frozenset(selected)

    @staticmethod
    def _matching(posting: frozenset[int], selected: frozenset[int] | None):
        return posting if selected is None else posting & selected

    def query_state(
        self, state_id: int, query_filter: QueryFilter | None = None
    ) -> GraphStateView:
        """Return context-valid continuations with distinct-game support."""
        try:
            state = self.states[state_id]
        except IndexError as error:
            raise KeyError(state_id) from error
        if state.id != state_id:
            raise KeyError(state_id)

        selected = self._selected_games(query_filter)
        position_matches = self._matching(
            self.position_games[state.position_id], selected
        )
        state_matches = self._matching(self.state_games[state_id], selected)
        ending_matches = self._matching(self.ending_games[state_id], selected)
        branches = []
        for edge in self._outgoing.get(state_id, ()):
            matches = self._matching(self.edge_games[edge.id], selected)
            if not matches:
                continue
            results = Counter(result_bucket(self.games[ordinal]) for ordinal in matches)
            branches.append(
                GraphBranch(
                    edge_id=edge.id,
                    child_position_id=edge.child_position_id,
                    child_state_id=edge.child_state_id,
                    move_token=edge.move_token,
                    move_label=edge.move_label,
                    support=len(matches),
                    results=tuple(sorted(results.items())),
                )
            )
        branches.sort(key=lambda branch: (-branch.support, branch.move_label, branch.edge_id))
        sole_game_uuid = (
            self.games[next(iter(state_matches))].uuid if len(state_matches) == 1 else None
        )
        return GraphStateView(
            position_id=state.position_id,
            state_id=state.id,
            position_fen=state.position_fen,
            position_support=len(position_matches),
            state_support=len(state_matches),
            actual_ending_count=len(ending_matches),
            branches=tuple(branches),
            sole_game_uuid=sole_game_uuid,
        )


def build_position_graph(
    games, *, source_fingerprint: str = "in-memory"
) -> PositionGraph:
    """Build the deterministic reference graph from a finite game iterable."""
    ordered_games = tuple(
        sorted(
            games,
            key=lambda game: (game.uuid, game.move_tokens, game.content_hash),
        )
    )
    if not ordered_games:
        raise ValueError("position graphs require at least one game")
    if any(not isinstance(game, OpeningGame) for game in ordered_games):
        raise TypeError("position graphs require OpeningGame records")

    position_keys = set()
    state_keys = set()
    edge_keys = set()
    edge_labels = {}
    per_game_positions = []
    per_game_states = []
    per_game_edges = []
    per_game_endings = []

    for game in ordered_games:
        board = Board()
        game_positions = {board.placement()}
        game_states = {board.position_key()}
        game_edges = set()
        position_keys.update(game_positions)
        state_keys.update(game_states)

        move_tokens = game.move_tokens
        decoded = decode_tcn("".join(move_tokens))
        if len(decoded) != len(move_tokens):
            raise GraphInvariantError(f"decoded move count changed for {game.uuid}")

        for move_token, move in zip(move_tokens, decoded, strict=True):
            parent_state = board.position_key()
            _move_id, move_label = label(board, move)
            board.apply(move)
            child_position = board.placement()
            child_state = board.position_key()
            edge_key = (parent_state, move_token, child_state)

            prior_label = edge_labels.setdefault(edge_key, move_label)
            if prior_label != move_label:
                raise GraphInvariantError(
                    f"edge label is not deterministic for {edge_key!r}"
                )
            position_keys.add(child_position)
            state_keys.add(child_state)
            edge_keys.add(edge_key)
            game_positions.add(child_position)
            game_states.add(child_state)
            game_edges.add(edge_key)

        per_game_positions.append(game_positions)
        per_game_states.append(game_states)
        per_game_edges.append(game_edges)
        per_game_endings.append(board.position_key())

    sorted_positions = sorted(
        position_keys, key=lambda placement: (identity_key("position", placement), placement)
    )
    position_ids = {placement: index for index, placement in enumerate(sorted_positions)}
    sorted_states = sorted(
        state_keys, key=lambda position_fen: (identity_key("state", position_fen), position_fen)
    )
    state_ids = {position_fen: index for index, position_fen in enumerate(sorted_states)}

    positions = tuple(
        GraphPosition(index, placement)
        for index, placement in enumerate(sorted_positions)
    )
    states = tuple(
        GraphState(index, position_ids[position_fen.split(" ", 1)[0]], position_fen)
        for index, position_fen in enumerate(sorted_states)
    )

    # A state plus token must replay deterministically.  Keeping the child in the
    # identity makes accidental conflicts visible instead of silently overwriting.
    parent_token_children = {}
    for parent_state, move_token, child_state in edge_keys:
        key = (parent_state, move_token)
        prior = parent_token_children.setdefault(key, child_state)
        if prior != child_state:
            raise GraphInvariantError(
                f"one state/token maps to multiple children: {key!r}"
            )

    sorted_edges = sorted(
        edge_keys,
        key=lambda edge: (
            state_ids[edge[0]],
            edge[1],
            state_ids[edge[2]],
        ),
    )
    edge_ids = {edge_key: index for index, edge_key in enumerate(sorted_edges)}
    edges = tuple(
        GraphEdge(
            id=index,
            parent_state_id=state_ids[parent_state],
            child_position_id=position_ids[child_state.split(" ", 1)[0]],
            child_state_id=state_ids[child_state],
            move_token=move_token,
            move_label=edge_labels[(parent_state, move_token, child_state)],
        )
        for index, (parent_state, move_token, child_state) in enumerate(sorted_edges)
    )

    position_games = [set() for _ in positions]
    state_games = [set() for _ in states]
    edge_games = [set() for _ in edges]
    ending_games = [set() for _ in states]
    for ordinal, (game_positions, game_states, game_edges, ending_state) in enumerate(
        zip(
            per_game_positions,
            per_game_states,
            per_game_edges,
            per_game_endings,
            strict=True,
        )
    ):
        for placement in game_positions:
            position_games[position_ids[placement]].add(ordinal)
        for position_fen in game_states:
            state_games[state_ids[position_fen]].add(ordinal)
        for edge_key in game_edges:
            edge_games[edge_ids[edge_key]].add(ordinal)
        ending_games[state_ids[ending_state]].add(ordinal)

    digest = hashlib.blake2b(digest_size=20)
    digest.update(b"opening-position-graph-v1\0")
    digest.update(source_fingerprint.encode())
    for game in ordered_games:
        for value in (game.uuid, "".join(game.move_tokens), game.content_hash):
            digest.update(b"\0")
            digest.update(value.encode())

    root_state_id = state_ids[Board().position_key()]
    return PositionGraph(
        build_id=digest.hexdigest(),
        games=ordered_games,
        positions=positions,
        states=states,
        edges=edges,
        position_games=tuple(frozenset(values) for values in position_games),
        state_games=tuple(frozenset(values) for values in state_games),
        edge_games=tuple(frozenset(values) for values in edge_games),
        ending_games=tuple(frozenset(values) for values in ending_games),
        root_state_id=root_state_id,
    )
