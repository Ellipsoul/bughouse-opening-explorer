"""Immutable prefix-interval packed trie with per-seat ordinal postings."""

from array import array
from bisect import bisect_left
import hashlib
import json
import mmap
from pathlib import Path
import struct
import sys
import time
import zlib

from .adapter import ADAPTER_POLICY_VERSION
from .model import Branch, NodeView, PrefixNotFound, QueryFilter, replay_prefix
from .trie import prepare_trie


NODE = struct.Struct("<iIIIIIIIi")
EDGE = struct.Struct("<2sI")
UINT32 = struct.Struct("<I")
UINT64 = struct.Struct("<Q")


class SortedPosting:
    """Binary-searchable uint32 posting list backed by mapped bytes."""

    def __init__(self, buffer, *, offset: int, count: int):
        self.buffer = buffer
        self.offset = offset
        self.count = count

    def _value(self, index):
        return UINT32.unpack_from(
            self.buffer, self.offset + index * UINT32.size
        )[0]

    def _lower_bound(self, value):
        left = 0
        right = self.count
        while left < right:
            middle = (left + right) // 2
            if self._value(middle) < value:
                left = middle + 1
            else:
                right = middle
        return left

    def count_between(self, start, end):
        return self._lower_bound(end) - self._lower_bound(start)

    def values_between(self, start, end):
        left = self._lower_bound(start)
        right = self._lower_bound(end)
        return tuple(self._value(index) for index in range(left, right))


def _file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_uint32s(stream, values):
    packed = array("I", values)
    if packed.itemsize != UINT32.size:
        raise RuntimeError("packed uint32 arrays require four-byte unsigned ints")
    if sys.byteorder != "little":
        packed.byteswap()
    packed.tofile(stream)


def build_packed_index(
    games, directory, *, source_fingerprint: str, postings: str = "sorted"
):
    if postings not in {"sorted", "bitmap"}:
        raise ValueError("postings must be 'sorted' or 'bitmap'")
    directory = Path(directory)
    if directory.exists():
        raise FileExistsError(directory)
    directory.mkdir(parents=True)
    prepared = prepare_trie(games, source_fingerprint=source_fingerprint)

    edges = []
    endings = []
    node_rows = []
    for node in prepared.nodes:
        edge_start = len(edges)
        edges.extend(
            (prepared.nodes[child].move_token, child) for child in node.children
        )
        ending_start = len(endings)
        endings.extend(node.endings)
        node_rows.append(
            (
                node.parent_id if node.parent_id is not None else -1,
                node.ply,
                node.interval_start,
                node.interval_end,
                edge_start,
                len(node.children),
                ending_start,
                len(node.endings),
                node.terminal_ordinal if node.terminal_ordinal is not None else -1,
            )
        )

    with (directory / "nodes.bin").open("wb") as stream:
        for row in node_rows:
            stream.write(NODE.pack(*row))
    with (directory / "edges.bin").open("wb") as stream:
        for token, child in edges:
            stream.write(EDGE.pack(token.encode("ascii"), child))
    with (directory / "endings.bin").open("wb") as stream:
        _write_uint32s(stream, endings)

    offsets = []
    with (directory / "games.jsonl").open("wb") as stream:
        for game in prepared.games:
            offsets.append(stream.tell())
            payload = {
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
            stream.write(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
            stream.write(b"\n")
        offsets.append(stream.tell())
    with (directory / "game_offsets.bin").open("wb") as stream:
        for offset in offsets:
            stream.write(UINT64.pack(offset))

    posting_values = {}
    for ordinal, game in enumerate(prepared.games):
        posting_values.setdefault(f"white\0{game.white_username}", []).append(ordinal)
        posting_values.setdefault(f"black\0{game.black_username}", []).append(ordinal)
        posting_values.setdefault(
            f"result\0{game.white_result or 'unknown'}", []
        ).append(ordinal)
    posting_index = {}
    with (directory / "postings.bin").open("wb") as stream:
        for key in sorted(posting_values):
            values = posting_values[key]
            if postings == "sorted":
                posting_index[key] = {
                    "offset": stream.tell(),
                    "count": len(values),
                }
                _write_uint32s(stream, values)
            else:
                bitmap = bytearray((len(prepared.games) + 7) // 8)
                for ordinal in values:
                    bitmap[ordinal // 8] |= 1 << (ordinal % 8)
                compressed = zlib.compress(bitmap, level=9)
                posting_index[key] = {
                    "offset": stream.tell(),
                    "bytes": len(compressed),
                    "count": len(values),
                }
                stream.write(compressed)
    (directory / "postings.json").write_text(
        json.dumps(posting_index, separators=(",", ":"), sort_keys=True)
    )

    files = [
        "edges.bin",
        "endings.bin",
        "game_offsets.bin",
        "games.jsonl",
        "nodes.bin",
        "postings.bin",
        "postings.json",
    ]
    manifest = {
        "adapter_policy": ADAPTER_POLICY_VERSION,
        "build_id": prepared.build_id,
        "dataset_version": prepared.build_id,
        "edge_record_bytes": EDGE.size,
        "edges": len(edges),
        "files": {
            name: {
                "bytes": (directory / name).stat().st_size,
                "sha256": _file_hash(directory / name),
            }
            for name in files
        },
        "games": len(prepared.games),
        "format_version": "packed-prefix-interval-v1",
        "node_record_bytes": NODE.size,
        "node_semantics": "exact-decoded-move-prefix-v1",
        "nodes": len(prepared.nodes),
        "postings": postings,
        "results": sorted({game.white_result or "unknown" for game in prepared.games}),
        "source_fingerprint": source_fingerprint,
        "terminal_policy": "first-distinct-support-one-or-game-end-v1",
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return prepared.build_id


class PackedIndex:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.manifest = json.loads((self.directory / "manifest.json").read_text())
        started = time.perf_counter_ns()
        self.posting_index = json.loads((self.directory / "postings.json").read_text())
        self.startup_profile = {
            "posting_directory_parse": {
                "bytes": (self.directory / "postings.json").stat().st_size,
                "records": len(self.posting_index),
                "scaling": "posting_directory_bytes",
                "wall_ms": (time.perf_counter_ns() - started) / 1_000_000,
            }
        }
        self._game_data_name = (
            "games.bin"
            if self.manifest.get("game_metadata_codec") == "zlib-json-v1"
            else "games.jsonl"
        )
        self._streams = []
        self._maps = {}
        started = time.perf_counter_ns()
        for name in (
            "nodes.bin",
            "edges.bin",
            "endings.bin",
            "game_offsets.bin",
            self._game_data_name,
            "postings.bin",
        ):
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
        self._posting_cache = {}

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

    def _node(self, node_id):
        return NODE.unpack_from(self._maps["nodes.bin"], node_id * NODE.size)

    def _children(self, node):
        edge_start, edge_count = node[4], node[5]
        for edge_index in range(edge_start, edge_start + edge_count):
            token, child = EDGE.unpack_from(
                self._maps["edges.bin"], edge_index * EDGE.size
            )
            yield token.decode("ascii"), child

    def _node_id(self, prefix):
        node_id = 0
        for wanted in prefix:
            for token, child in self._children(self._node(node_id)):
                if token == wanted:
                    node_id = child
                    break
            else:
                raise PrefixNotFound(prefix)
        return node_id

    def _posting(self, key):
        if key not in self._posting_cache:
            record = self.posting_index.get(key)
            if record is None:
                values = (
                    SortedPosting(b"", offset=0, count=0)
                    if self.manifest["postings"] == "sorted"
                    else b""
                )
            elif self.manifest["postings"] == "bitmap":
                offset = record["offset"]
                values = zlib.decompress(
                    self._maps["postings.bin"][offset : offset + record["bytes"]]
                )
            else:
                values = SortedPosting(
                    self._maps["postings.bin"],
                    offset=record["offset"],
                    count=record["count"],
                )
            self._posting_cache[key] = values
        return self._posting_cache[key]

    def _selected(self, query_filter, start, end):
        keys = []
        if query_filter.white_username:
            keys.append(f"white\0{query_filter.white_username}")
        if query_filter.black_username:
            keys.append(f"black\0{query_filter.black_username}")
        if self.manifest["postings"] == "bitmap":
            bitmaps = [self._posting(key) for key in keys]
            selected = []
            first_byte = start // 8
            last_byte = (end - 1) // 8 if end > start else first_byte - 1
            for byte_index in range(first_byte, last_byte + 1):
                value = 0xFF
                for bitmap in bitmaps:
                    value &= bitmap[byte_index] if byte_index < len(bitmap) else 0
                if byte_index == first_byte:
                    value &= 0xFF << (start % 8)
                if byte_index == last_byte and end % 8:
                    value &= (1 << (end % 8)) - 1
                while value:
                    bit = (value & -value).bit_length() - 1
                    selected.append(byte_index * 8 + bit)
                    value &= value - 1
            return tuple(selected)
        postings = [self._posting(key) for key in keys]
        slices = [
            posting.values_between(start, end)
            for posting in postings
        ]
        if len(slices) == 1:
            return tuple(slices[0])
        left, right = slices
        selected = []
        left_index = right_index = 0
        while left_index < len(left) and right_index < len(right):
            if left[left_index] == right[right_index]:
                selected.append(left[left_index])
                left_index += 1
                right_index += 1
            elif left[left_index] < right[right_index]:
                left_index += 1
            else:
                right_index += 1
        return tuple(selected)

    def _posting_count(self, key, start, end):
        posting = self._posting(key)
        if self.manifest["postings"] == "sorted":
            return posting.count_between(start, end)
        count = 0
        first_byte = start // 8
        last_byte = (end - 1) // 8 if end > start else first_byte - 1
        for byte_index in range(first_byte, last_byte + 1):
            value = posting[byte_index] if byte_index < len(posting) else 0
            if byte_index == first_byte:
                value &= 0xFF << (start % 8)
            if byte_index == last_byte and end % 8:
                value &= (1 << (end % 8)) - 1
            count += value.bit_count()
        return count

    def _game(self, ordinal):
        offsets = self._maps["game_offsets.bin"]
        start = UINT64.unpack_from(offsets, ordinal * UINT64.size)[0]
        end = UINT64.unpack_from(offsets, (ordinal + 1) * UINT64.size)[0]
        payload = self._maps[self._game_data_name][start:end]
        if self.manifest.get("game_metadata_codec") == "zlib-json-v1":
            payload = zlib.decompress(payload)
        return json.loads(payload)

    def query(self, prefix=(), query_filter: QueryFilter | None = None):
        prefix = tuple(prefix)
        node_id = self._node_id(prefix)
        node = self._node(node_id)
        start, end = node[2], node[3]
        selected = None
        if query_filter and (
            query_filter.white_username or query_filter.black_username
        ):
            selected = self._selected(query_filter, start, end)
        support = end - start if selected is None else len(selected)

        ending_start, ending_count = node[6], node[7]
        ending_ordinals = tuple(
            UINT32.unpack_from(
                self._maps["endings.bin"], (ending_start + index) * UINT32.size
            )[0]
            for index in range(ending_count)
        )
        if selected is not None:
            selected_set = set(selected)
            ending_ordinals = tuple(
                ordinal for ordinal in ending_ordinals if ordinal in selected_set
            )

        sole_ordinal = None
        if selected is not None and len(selected) == 1:
            sole_ordinal = selected[0]
            branches = ()
        else:
            if selected is None and node[8] >= 0:
                sole_ordinal = node[8]
            branch_records = []
            for token, child_id in self._children(node):
                child = self._node(child_id)
                if selected is None:
                    child_support = child[3] - child[2]
                else:
                    child_support = bisect_left(selected, child[3]) - bisect_left(
                        selected, child[2]
                    )
                if child_support:
                    if selected is None:
                        results = tuple(
                            (result, count)
                            for result in self.manifest["results"]
                            if (
                                count := self._posting_count(
                                    f"result\0{result}", child[2], child[3]
                                )
                            )
                        )
                    else:
                        slice_start = bisect_left(selected, child[2])
                        slice_end = bisect_left(selected, child[3])
                        result_counts = {}
                        for ordinal in selected[slice_start:slice_end]:
                            result = self._game(ordinal)["white_result"] or "unknown"
                            result_counts[result] = result_counts.get(result, 0) + 1
                        results = tuple(sorted(result_counts.items()))
                    branch_records.append(Branch(token, child_support, results))
            branches = tuple(branch_records)

        return NodeView(
            prefix=prefix,
            position_fen=replay_prefix(prefix),
            support=support,
            branches=branches,
            ended_game_uuids=tuple(
                self._game(ordinal)["uuid"] for ordinal in ending_ordinals
            ),
            sole_game_uuid=(
                self._game(sole_ordinal)["uuid"] if sole_ordinal is not None else None
            ),
        )
