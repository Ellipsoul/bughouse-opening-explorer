"""Sorted-radix construction for the logical support-aware prefix trie."""

from dataclasses import dataclass, field
import hashlib

from .adapter import OpeningGame


@dataclass
class TrieNode:
    id: int
    parent_id: int | None
    move_token: str | None
    ply: int
    interval_start: int
    interval_end: int
    terminal_ordinal: int | None
    endings: tuple[int, ...]
    children: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class PreparedTrie:
    games: tuple[OpeningGame, ...]
    nodes: tuple[TrieNode, ...]
    build_id: str


def prepare_trie(games, *, source_fingerprint: str) -> PreparedTrie:
    ordered = tuple(sorted(games, key=lambda game: (game.move_tokens, game.uuid)))
    digest = hashlib.blake2b(digest_size=20)
    digest.update(b"opening-trie-v1\0")
    digest.update(source_fingerprint.encode())
    for game in ordered:
        digest.update(b"\0")
        digest.update(game.uuid.encode())
        digest.update(b"\0")
        digest.update("".join(game.move_tokens).encode())
        digest.update(b"\0")
        digest.update(game.content_hash.encode())

    nodes = []
    stack = [(0, len(ordered), 0, None, None)] if ordered else []
    while stack:
        start, end, ply, parent_id, move_token = stack.pop()
        node_id = len(nodes)
        cursor = start
        while cursor < end and len(ordered[cursor].move_tokens) == ply:
            cursor += 1
        node = TrieNode(
            id=node_id,
            parent_id=parent_id,
            move_token=move_token,
            ply=ply,
            interval_start=start,
            interval_end=end,
            terminal_ordinal=start if end - start == 1 else None,
            endings=tuple(range(start, cursor)),
        )
        nodes.append(node)
        if parent_id is not None:
            nodes[parent_id].children.append(node_id)
        if end - start == 1:
            continue

        children = []
        child_start = cursor
        while child_start < end:
            token = ordered[child_start].move_tokens[ply]
            child_end = child_start + 1
            while child_end < end and ordered[child_end].move_tokens[ply] == token:
                child_end += 1
            children.append((child_start, child_end, ply + 1, node_id, token))
            child_start = child_end
        stack.extend(reversed(children))

    return PreparedTrie(ordered, tuple(nodes), digest.hexdigest())
