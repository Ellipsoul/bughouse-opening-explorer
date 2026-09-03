"""Immutable packed representation of the transposition-aware position graph."""

from array import array
from bisect import bisect_left
from collections import Counter, defaultdict
import json
import mmap
from pathlib import Path
import struct
import sys
import time
import uuid
import zlib

from .adapter import ADAPTER_POLICY_VERSION
from .model import QueryFilter
from .packed import _file_hash
from .position_graph import (
    GraphBranch,
    GraphStateView,
    build_position_graph,
    result_bucket,
)


UINT32 = struct.Struct("<I")
UINT64 = struct.Struct("<Q")
POSITION_V1 = struct.Struct("<QIQI")
STATE_V1 = struct.Struct("<IQIQIQIIIIBBB")
EDGE_V1 = struct.Struct("<II2sQIQIIII")

# v2 keeps all public IDs and semantic fields, but uses bounds proven by the
# full v1 corpus.  Loss counts and an edge's child position are derivable.
POSITION_V2 = struct.Struct("<IBII")
STATE_V2 = struct.Struct("<IIBIIIHIIBBB")
EDGE_V2 = struct.Struct("<I2sIBIIII")
GAME_V2 = struct.Struct("<16sQIIHHBBBB")

# Backwards-compatible names used by the v1 writers and validator.
POSITION = POSITION_V1
STATE = STATE_V1
EDGE = EDGE_V1


def _state_context(position_fen):
    _placement, side, castling, ep = position_fen.split(" ")
    castling_mask = sum(
        1 << index for index, right in enumerate("KQkq") if right in castling
    )
    ep_square = (
        255
        if ep == "-"
        else (int(ep[1]) - 1) * 8 + ord(ep[0]) - ord("a")
    )
    return int(side == "b"), castling_mask, ep_square


def _position_fen(placement, side, castling_mask, ep_square):
    color = "b" if side else "w"
    castling = "".join(
        right
        for index, right in enumerate("KQkq")
        if castling_mask & (1 << index)
    ) or "-"
    ep = (
        "-"
        if ep_square == 255
        else f"{'abcdefgh'[ep_square % 8]}{ep_square // 8 + 1}"
    )
    return f"{placement} {color} {castling} {ep}"


def _write_uint32s(stream, values):
    packed = array("I", values)
    if packed.itemsize != UINT32.size:
        raise RuntimeError("packed graph requires four-byte unsigned ints")
    if sys.byteorder != "little":
        packed.byteswap()
    packed.tofile(stream)


def _metadata_payload(game):
    return {
        "black_rating": game.black_rating,
        "black_result": game.black_result,
        "black_username": game.black_username,
        "content_hash": game.content_hash,
        "end_time": game.end_time,
        "provenance_flags": game.provenance_flags,
        "rated": game.rated,
        "source": game.source,
        "time_control": game.time_control,
        "url": game.url,
        "uuid": game.uuid,
        "white_rating": game.white_rating,
        "white_result": game.white_result,
        "white_username": game.white_username,
    }


def _outcome_counts(games, ordinals):
    counts = Counter(result_bucket(games[ordinal]) for ordinal in ordinals)
    return counts["win"], counts["draw"], counts["loss"]


def build_packed_position_graph(games, directory, *, source_fingerprint: str):
    """Build a small-corpus packed artifact through the semantic oracle.

    Full-corpus construction uses the streaming builder.  Keeping this writer
    intentionally simple gives that implementation an independent reference.
    """
    directory = Path(directory)
    if directory.exists():
        raise FileExistsError(directory)
    directory.mkdir(parents=True)
    graph = build_position_graph(games, source_fingerprint=source_fingerprint)

    strings_path = directory / "strings.bin"
    memberships_path = directory / "memberships.bin"
    position_rows = []
    state_rows = []
    edge_rows = []
    edge_groups = defaultdict(list)
    for edge in graph.edges:
        edge_groups[edge.parent_state_id].append(edge)

    membership_cursor = 0
    with strings_path.open("wb") as strings, memberships_path.open("wb") as memberships:
        for position in graph.positions:
            encoded = position.placement.encode("ascii")
            string_offset = strings.tell()
            strings.write(encoded)
            posting = sorted(graph.position_games[position.id])
            posting_start = membership_cursor
            _write_uint32s(memberships, posting)
            membership_cursor += len(posting)
            position_rows.append(
                (string_offset, len(encoded), posting_start, len(posting))
            )

        next_edge_id = 0
        for state in graph.states:
            state_posting = sorted(graph.state_games[state.id])
            state_start = membership_cursor
            _write_uint32s(memberships, state_posting)
            membership_cursor += len(state_posting)
            ending_posting = sorted(graph.ending_games[state.id])
            ending_start = membership_cursor
            _write_uint32s(memberships, ending_posting)
            membership_cursor += len(ending_posting)
            outgoing = sorted(edge_groups.get(state.id, ()), key=lambda edge: edge.id)
            if outgoing and outgoing[0].id != next_edge_id:
                raise ValueError("graph edges are not grouped by parent state")
            state_rows.append(
                (
                    state.position_id,
                    next_edge_id,
                    len(outgoing),
                    state_start,
                    len(state_posting),
                    ending_start,
                    len(ending_posting),
                    *_outcome_counts(graph.games, state_posting),
                    *_state_context(state.position_fen),
                )
            )
            for edge in outgoing:
                label_bytes = edge.move_label.encode("utf-8")
                label_offset = strings.tell()
                strings.write(label_bytes)
                edge_posting = sorted(graph.edge_games[edge.id])
                edge_start = membership_cursor
                _write_uint32s(memberships, edge_posting)
                membership_cursor += len(edge_posting)
                edge_rows.append(
                    (
                        edge.child_position_id,
                        edge.child_state_id,
                        edge.move_token.encode("ascii"),
                        label_offset,
                        len(label_bytes),
                        edge_start,
                        len(edge_posting),
                        *_outcome_counts(graph.games, edge_posting),
                    )
                )
                next_edge_id += 1

    with (directory / "positions.bin").open("wb") as stream:
        for row in position_rows:
            stream.write(POSITION.pack(*row))
    with (directory / "states.bin").open("wb") as stream:
        for row in state_rows:
            stream.write(STATE.pack(*row))
    with (directory / "edges.bin").open("wb") as stream:
        for row in edge_rows:
            stream.write(EDGE.pack(*row))

    with (directory / "games.bin").open("wb") as games_stream, (
        directory / "game_offsets.bin"
    ).open("wb") as offsets_stream:
        for game in graph.games:
            offsets_stream.write(UINT64.pack(games_stream.tell()))
            games_stream.write(
                zlib.compress(
                    json.dumps(
                        _metadata_payload(game), separators=(",", ":"), sort_keys=True
                    ).encode(),
                    level=6,
                )
            )
        offsets_stream.write(UINT64.pack(games_stream.tell()))

    posting_values = defaultdict(list)
    for ordinal, game in enumerate(graph.games):
        posting_values[f"white\0{game.white_username.casefold()}"].append(ordinal)
        posting_values[f"black\0{game.black_username.casefold()}"].append(ordinal)
    posting_index = {}
    with (directory / "postings.bin").open("wb") as stream:
        for key in sorted(posting_values):
            values = posting_values[key]
            posting_index[key] = {"offset": stream.tell(), "count": len(values)}
            _write_uint32s(stream, values)
    (directory / "postings.json").write_text(
        json.dumps(posting_index, separators=(",", ":"), sort_keys=True)
    )

    files = [
        "edges.bin",
        "game_offsets.bin",
        "games.bin",
        "memberships.bin",
        "positions.bin",
        "postings.bin",
        "postings.json",
        "states.bin",
        "strings.bin",
    ]
    manifest = {
        "adapter_policy": ADAPTER_POLICY_VERSION,
        "build_id": graph.build_id,
        "dataset_version": graph.build_id,
        "edges": len(graph.edges),
        "files": {
            name: {
                "bytes": (directory / name).stat().st_size,
                "sha256": _file_hash(directory / name),
            }
            for name in files
        },
        "format_version": "packed-position-graph-v1",
        "games": len(graph.games),
        "node_semantics": "piece-placement-v1",
        "position_record_bytes": POSITION.size,
        "positions": len(graph.positions),
        "root_node_id": graph.root_position_id,
        "root_state_id": graph.root_state_id,
        "replay_policy": "strict-source-game-v1",
        "source_fingerprint": source_fingerprint,
        "state_record_bytes": STATE.size,
        "state_semantics": "side-castling-en-passant-v1",
        "states": len(graph.states),
        "support_semantics": "distinct-game-membership-v1",
        "terminal_policy": "full-replay-game-end-v1",
        "edge_record_bytes": EDGE.size,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return graph.build_id


class _Posting:
    def __init__(self, buffer, start: int, count: int):
        self.buffer = buffer
        self.start = start
        self.count = count

    def value(self, index: int) -> int:
        return UINT32.unpack_from(
            self.buffer, (self.start + index) * UINT32.size
        )[0]

    def values(self):
        return tuple(self.value(index) for index in range(self.count))

    def contains(self, value: int) -> bool:
        left = 0
        right = self.count
        while left < right:
            middle = (left + right) // 2
            current = self.value(middle)
            if current < value:
                left = middle + 1
            else:
                right = middle
        return left < self.count and self.value(left) == value


class _SelectedGames(tuple):
    """Sorted selected ordinals with an O(1) lookup for small postings."""

    def __new__(cls, values):
        selected = super().__new__(cls, values)
        selected.lookup = frozenset(selected)
        return selected


class PackedPositionGraph:
    """Memory-mapped graph reader; startup work scales with file count."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.manifest = json.loads((self.directory / "manifest.json").read_text())
        self.format_version = self.manifest.get("format_version")
        if self.format_version not in {
            "packed-position-graph-v1",
            "packed-position-graph-v2",
        }:
            raise ValueError("not a packed position graph")
        self._position_record = (
            POSITION_V2
            if self.format_version == "packed-position-graph-v2"
            else POSITION_V1
        )
        self._state_record = (
            STATE_V2
            if self.format_version == "packed-position-graph-v2"
            else STATE_V1
        )
        self._edge_record = (
            EDGE_V2
            if self.format_version == "packed-position-graph-v2"
            else EDGE_V1
        )
        if self.manifest.get("position_record_bytes") != self._position_record.size:
            raise ValueError("position record size mismatch")
        if self.manifest.get("state_record_bytes") != self._state_record.size:
            raise ValueError("state record size mismatch")
        if self.manifest.get("edge_record_bytes") != self._edge_record.size:
            raise ValueError("edge record size mismatch")
        self.root_position_id = self.manifest["root_node_id"]
        self.root_state_id = self.manifest["root_state_id"]
        started = time.perf_counter_ns()
        self.posting_index = json.loads((self.directory / "postings.json").read_text())
        if self.format_version == "packed-position-graph-v2":
            self.game_dictionaries = json.loads(
                (self.directory / "game_dictionaries.json").read_text()
            )
        self.startup_profile = {
            "posting_directory_parse": {
                "bytes": (self.directory / "postings.json").stat().st_size,
                "records": len(self.posting_index),
                "scaling": "posting_directory_bytes",
                "wall_ms": (time.perf_counter_ns() - started) / 1_000_000,
            }
        }
        self._streams = []
        self._maps = {}
        started = time.perf_counter_ns()
        mapped_names = [
            "positions.bin",
            "states.bin",
            "edges.bin",
            "strings.bin",
            "memberships.bin",
            "games.bin",
            "postings.bin",
        ]
        if self.format_version == "packed-position-graph-v1":
            mapped_names.append("game_offsets.bin")
        else:
            mapped_names.extend(("username_offsets.bin", "usernames.bin"))
        for name in mapped_names:
            stream = (self.directory / name).open("rb")
            self._streams.append(stream)
            self._maps[name] = (
                mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
                if (self.directory / name).stat().st_size
                else None
            )
        self.startup_profile["mmap_construction"] = {
            "files": len(self._streams),
            "mapped_bytes": sum(
                (self.directory / name).stat().st_size for name in self._maps
            ),
            "scaling": "mapped_file_count",
            "wall_ms": (time.perf_counter_ns() - started) / 1_000_000,
        }

    def close(self):
        for mapped in self._maps.values():
            if mapped is not None:
                mapped.close()
        for stream in self._streams:
            stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def _position(self, position_id):
        if not 0 <= position_id < self.manifest["positions"]:
            raise KeyError(position_id)
        return self._position_record.unpack_from(
            self._maps["positions.bin"], position_id * self._position_record.size
        )

    def _state(self, state_id):
        if not 0 <= state_id < self.manifest["states"]:
            raise KeyError(state_id)
        state = self._state_record.unpack_from(
            self._maps["states.bin"], state_id * self._state_record.size
        )
        if self.format_version == "packed-position-graph-v1":
            return state
        (
            position_id,
            edge_start,
            edge_count,
            game_start,
            game_count,
            ending_start,
            ending_count,
            wins,
            draws,
            side,
            castling_mask,
            ep_square,
        ) = state
        return (
            position_id,
            edge_start,
            edge_count,
            game_start,
            game_count,
            ending_start,
            ending_count,
            wins,
            draws,
            game_count - wins - draws,
            side,
            castling_mask,
            ep_square,
        )

    def _edge(self, edge_id):
        if not 0 <= edge_id < self.manifest["edges"]:
            raise KeyError(edge_id)
        edge = self._edge_record.unpack_from(
            self._maps["edges.bin"], edge_id * self._edge_record.size
        )
        if self.format_version == "packed-position-graph-v1":
            return edge
        (
            child_state_id,
            move_token,
            label_offset,
            label_length,
            game_start,
            game_count,
            wins,
            draws,
        ) = edge
        child_position_id = self._state(child_state_id)[0]
        return (
            child_position_id,
            child_state_id,
            move_token,
            label_offset,
            label_length,
            game_start,
            game_count,
            wins,
            draws,
            game_count - wins - draws,
        )

    def _string(self, offset, length, *, encoding="ascii"):
        return bytes(self._maps["strings.bin"][offset : offset + length]).decode(encoding)

    def _membership(self, start, count):
        return _Posting(self._maps["memberships.bin"], start, count)

    def _player_posting(self, seat, username):
        record = self.posting_index.get(f"{seat}\0{username.casefold()}")
        if record is None:
            return _Posting(b"", 0, 0)
        return _Posting(
            self._maps["postings.bin"],
            record["offset"] // UINT32.size,
            record["count"],
        )

    def _selected(self, query_filter):
        if query_filter is None:
            return None
        postings = []
        if query_filter.white_username is not None:
            postings.append(
                self._player_posting("white", query_filter.white_username).values()
            )
        if query_filter.black_username is not None:
            postings.append(
                self._player_posting("black", query_filter.black_username).values()
            )
        if not postings:
            return None
        selected = postings[0]
        for posting in postings[1:]:
            allowed = set(posting)
            selected = tuple(value for value in selected if value in allowed)
        return _SelectedGames(selected)

    @staticmethod
    def _matches(posting, selected):
        if selected is None:
            return posting.values()
        if not posting.count or not selected:
            return ()
        # Probe a large posting for each selected game, but scan a smaller
        # posting once against the selection's hash set.  The former costs
        # O(selected * log(posting)); the latter O(posting).  Full-corpus
        # popular-player filters otherwise repeat tens of millions of binary
        # searches across one neighborhood.
        probe_cost = len(selected) * max(1, posting.count.bit_length())
        if posting.count <= probe_cost:
            return tuple(
                value
                for index in range(posting.count)
                if (value := posting.value(index)) in selected.lookup
            )
        return tuple(value for value in selected if posting.contains(value))

    def selected_games(self, query_filter: QueryFilter | None):
        return self._selected(query_filter)

    def position_structure(self, position_id: int):
        string_offset, string_length, game_start, game_count = self._position(position_id)
        return {
            "id": position_id,
            "placement": self._string(string_offset, string_length),
            "support": game_count,
            "_game_start": game_start,
        }

    def state_structure(self, state_id: int):
        state = self._state(state_id)
        position = self.position_structure(state[0])
        return {
            "id": state_id,
            "node_id": state[0],
            "position_fen": _position_fen(position["placement"], *state[10:13]),
            "outgoing_count": state[2],
            "_edge_start": state[1],
            "_game_start": state[3],
            "_game_count": state[4],
            "_ending_start": state[5],
            "_ending_count": state[6],
            "_wins": state[7],
            "_draws": state[8],
            "_losses": state[9],
        }

    def outgoing_edges(self, state_id: int):
        state = self._state(state_id)
        values = []
        for edge_id in range(state[1], state[1] + state[2]):
            edge = self._edge(edge_id)
            values.append(
                {
                    "id": edge_id,
                    "parent_state_id": state_id,
                    "child_id": edge[0],
                    "child_state_id": edge[1],
                    "move_token": edge[2].decode("ascii"),
                    "move_label": self._string(edge[3], edge[4], encoding="utf-8"),
                    "_game_start": edge[5],
                    "_game_count": edge[6],
                    "_wins": edge[7],
                    "_draws": edge[8],
                    "_losses": edge[9],
                }
            )
        return tuple(values)

    def matching_position_games(self, position_id: int, selected=None):
        _offset, _length, start, count = self._position(position_id)
        return self._matches(self._membership(start, count), selected)

    def matching_state_games(self, state_id: int, selected=None):
        state = self._state(state_id)
        return self._matches(self._membership(state[3], state[4]), selected)

    def matching_ending_games(self, state_id: int, selected=None):
        state = self._state(state_id)
        return self._matches(self._membership(state[5], state[6]), selected)

    def matching_edge_games(self, edge_id: int, selected=None):
        edge = self._edge(edge_id)
        return self._matches(self._membership(edge[5], edge[6]), selected)

    def game(self, ordinal):
        if not 0 <= ordinal < self.manifest["games"]:
            raise KeyError(ordinal)
        if self.format_version == "packed-position-graph-v2":
            (
                uuid_bytes,
                numeric_url,
                white_username_id,
                black_username_id,
                white_rating,
                black_rating,
                white_result_id,
                black_result_id,
                source_id,
                provenance_id,
            ) = GAME_V2.unpack_from(
                self._maps["games.bin"], ordinal * GAME_V2.size
            )

            def username(username_id):
                offsets = self._maps["username_offsets.bin"]
                start = UINT32.unpack_from(offsets, username_id * UINT32.size)[0]
                end = UINT32.unpack_from(offsets, (username_id + 1) * UINT32.size)[0]
                return bytes(self._maps["usernames.bin"][start:end]).decode("utf-8")

            return {
                "black_rating": None if black_rating == 0xFFFF else black_rating,
                "black_result": self.game_dictionaries["results"][black_result_id],
                "black_username": username(black_username_id),
                "provenance_flags": self.game_dictionaries[
                    "provenance_flag_sets"
                ][provenance_id],
                "source": self.game_dictionaries["sources"][source_id],
                "url": (
                    None
                    if numeric_url == 0xFFFFFFFFFFFFFFFF
                    else f"https://www.chess.com/game/live/{numeric_url}"
                ),
                "uuid": str(uuid.UUID(bytes=uuid_bytes)),
                "white_rating": None if white_rating == 0xFFFF else white_rating,
                "white_result": self.game_dictionaries["results"][white_result_id],
                "white_username": username(white_username_id),
            }
        offsets = self._maps["game_offsets.bin"]
        start = UINT64.unpack_from(offsets, ordinal * UINT64.size)[0]
        end = UINT64.unpack_from(offsets, (ordinal + 1) * UINT64.size)[0]
        return json.loads(zlib.decompress(self._maps["games.bin"][start:end]))

    def query_state(self, state_id: int, query_filter: QueryFilter | None = None):
        (
            position_id,
            edge_start,
            edge_count,
            state_game_start,
            state_game_count,
            ending_start,
            ending_count,
            _state_wins,
            _state_draws,
            _state_losses,
            side,
            castling_mask,
            ep_square,
        ) = self._state(state_id)
        placement_offset, placement_length, position_game_start, position_game_count = (
            self._position(position_id)
        )
        placement = self._string(placement_offset, placement_length)
        selected = self._selected(query_filter)
        if selected is None:
            position_support = position_game_count
            state_support = state_game_count
            actual_ending_count = ending_count
            sole_ordinal = (
                self._membership(state_game_start, state_game_count).value(0)
                if state_game_count == 1
                else None
            )
        else:
            position_matches = self._matches(
                self._membership(position_game_start, position_game_count), selected
            )
            state_matches = self._matches(
                self._membership(state_game_start, state_game_count), selected
            )
            ending_matches = self._matches(
                self._membership(ending_start, ending_count), selected
            )
            position_support = len(position_matches)
            state_support = len(state_matches)
            actual_ending_count = len(ending_matches)
            sole_ordinal = state_matches[0] if len(state_matches) == 1 else None
        branches = []
        for edge_id in range(edge_start, edge_start + edge_count):
            (
                child_position_id,
                child_state_id,
                move_token,
                label_offset,
                label_length,
                game_start,
                game_count,
                wins,
                draws,
                losses,
            ) = self._edge(edge_id)
            if selected is None:
                support = game_count
                if not support:
                    continue
            else:
                edge_matches = self._matches(
                    self._membership(game_start, game_count), selected
                )
                support = len(edge_matches)
                if not support:
                    continue
                result_counts = Counter(
                    (
                        "win"
                        if (metadata := self.game(ordinal))["white_result"] == "win"
                        else "draw"
                        if metadata["white_result"] in {
                            "50move",
                            "agreed",
                            "insufficient",
                            "repetition",
                            "stalemate",
                            "timevsinsufficient",
                            "timevsinsufficientmaterial",
                        }
                        or metadata["black_result"] in {
                            "50move",
                            "agreed",
                            "insufficient",
                            "repetition",
                            "stalemate",
                            "timevsinsufficient",
                            "timevsinsufficientmaterial",
                        }
                        else "loss"
                    )
                    for ordinal in edge_matches
                )
                results = tuple(sorted(result_counts.items()))
            if selected is None:
                results = tuple(
                    (name, count)
                    for name, count in (("draw", draws), ("loss", losses), ("win", wins))
                    if count
                )
            branches.append(
                GraphBranch(
                    edge_id=edge_id,
                    child_position_id=child_position_id,
                    child_state_id=child_state_id,
                    move_token=move_token.decode("ascii"),
                    move_label=self._string(label_offset, label_length, encoding="utf-8"),
                    support=support,
                    results=results,
                )
            )
        branches.sort(key=lambda branch: (-branch.support, branch.move_label, branch.edge_id))
        return GraphStateView(
            position_id=position_id,
            state_id=state_id,
            position_fen=_position_fen(placement, side, castling_mask, ep_square),
            position_support=position_support,
            state_support=state_support,
            actual_ending_count=actual_ending_count,
            branches=tuple(branches),
            sole_game_uuid=(
                self.game(sole_ordinal)["uuid"] if sole_ordinal is not None else None
            ),
        )
