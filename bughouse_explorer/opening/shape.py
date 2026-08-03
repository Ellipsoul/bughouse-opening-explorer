"""Exact move-prefix trie shape measurement without board-position merging."""

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .adapter import OpeningGame


@dataclass(frozen=True)
class TrieShape:
    games: int
    plies: int
    nodes_by_ply: dict[int, int]
    branching_distribution: dict[int, int]
    terminal_depths: dict[int, int]
    identical_complete_line_groups: int
    games_in_identical_complete_lines: int
    games_ending_at_internal_nodes: int
    membership_entries: int
    interval_nodes: int
    edges: int
    patricia_removable_nodes: int


def measure_trie_shape(games: Iterable[OpeningGame]) -> TrieShape:
    """Measure the support-one trie constructed from lexically sorted games."""
    ordered = sorted(games, key=lambda game: (game.move_tokens, game.uuid))
    nodes_by_ply = Counter()
    branching = Counter()
    terminal_depth_by_game = [None] * len(ordered)
    membership_entries = 0
    internal_endings = 0
    patricia_removable = 0

    stack = [(0, len(ordered), 0, True)] if ordered else []
    while stack:
        start, end, ply, is_root = stack.pop()
        support = end - start
        nodes_by_ply[ply] += 1
        membership_entries += support

        if support == 1:
            terminal_depth_by_game[start] = ply
            branching[0] += 1
            continue

        cursor = start
        while cursor < end and len(ordered[cursor].move_tokens) == ply:
            terminal_depth_by_game[cursor] = ply
            cursor += 1

        children = []
        child_start = cursor
        while child_start < end:
            token = ordered[child_start].move_tokens[ply]
            child_end = child_start + 1
            while (
                child_end < end
                and ordered[child_end].move_tokens[ply] == token
            ):
                child_end += 1
            children.append((child_start, child_end, ply + 1, False))
            child_start = child_end

        branching[len(children)] += 1
        if cursor > start and children:
            internal_endings += cursor - start
        if not is_root and cursor == start and len(children) == 1:
            patricia_removable += 1
        stack.extend(reversed(children))

    line_counts = Counter(game.move_tokens for game in ordered)
    duplicate_counts = [count for count in line_counts.values() if count > 1]
    terminal_depths = Counter(terminal_depth_by_game)
    terminal_depths.pop(None, None)
    interval_nodes = sum(nodes_by_ply.values())
    return TrieShape(
        games=len(ordered),
        plies=sum(len(game.move_tokens) for game in ordered),
        nodes_by_ply=dict(sorted(nodes_by_ply.items())),
        branching_distribution=dict(sorted(branching.items())),
        terminal_depths=dict(sorted(terminal_depths.items())),
        identical_complete_line_groups=len(duplicate_counts),
        games_in_identical_complete_lines=sum(duplicate_counts),
        games_ending_at_internal_nodes=internal_endings,
        membership_entries=membership_entries,
        interval_nodes=interval_nodes,
        edges=max(0, interval_nodes - 1),
        patricia_removable_nodes=patricia_removable,
    )


def _common_prefix(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    limit = min(len(left), len(right))
    depth = 0
    while depth < limit and left[depth] == right[depth]:
        depth += 1
    return depth


def measure_sorted_token_lines(
    lines: Iterable[tuple[tuple[str, ...], str]],
) -> TrieShape:
    """Measure a sorted token/UUID stream with only adjacent-line lookahead."""
    iterator = iter(lines)
    try:
        current = next(iterator)
    except StopIteration:
        return TrieShape(0, 0, {}, {}, {}, 0, 0, 0, 0, 0, 0, 0)

    try:
        following = next(iterator)
    except StopIteration:
        following = None

    nodes_by_ply = Counter()
    branching = Counter()
    terminal_depths = Counter()
    active = []
    previous_sequence = None
    previous_terminal = 0
    games = 0
    plies = 0
    membership_entries = 0
    internal_endings = 0
    patricia_removable = 0
    duplicate_groups = 0
    duplicate_games = 0
    run_sequence = None
    run_count = 0

    def close_to(depth):
        nonlocal internal_endings, patricia_removable
        while len(active) - 1 > depth:
            node = active.pop()
            branching[node["children"]] += 1
            if node["children"] and node["endings"]:
                internal_endings += node["endings"]
            if node["depth"] > 0 and node["children"] == 1 and not node["endings"]:
                patricia_removable += 1

    while True:
        sequence, _uuid = current
        next_sequence = following[0] if following is not None else None
        left_lcp = (
            _common_prefix(previous_sequence, sequence)
            if previous_sequence is not None
            else 0
        )
        right_lcp = (
            _common_prefix(sequence, next_sequence)
            if next_sequence is not None
            else 0
        )
        if previous_sequence is None and next_sequence is None:
            terminal = 0
        else:
            terminal = min(len(sequence), max(left_lcp, right_lcp) + 1)

        common_active = (
            0
            if previous_sequence is None
            else min(left_lcp, previous_terminal, terminal)
        )
        close_to(common_active)
        start_depth = 0 if not active else common_active + 1
        for depth in range(start_depth, terminal + 1):
            if depth > 0:
                active[-1]["children"] += 1
            active.append({"depth": depth, "children": 0, "endings": 0})
            nodes_by_ply[depth] += 1

        if terminal == len(sequence):
            active[terminal]["endings"] += 1
        terminal_depths[terminal] += 1
        games += 1
        plies += len(sequence)
        membership_entries += terminal + 1

        if run_sequence == sequence:
            run_count += 1
        else:
            if run_count > 1:
                duplicate_groups += 1
                duplicate_games += run_count
            run_sequence = sequence
            run_count = 1

        previous_sequence = sequence
        previous_terminal = terminal
        if following is None:
            break
        current = following
        try:
            following = next(iterator)
        except StopIteration:
            following = None

    if run_count > 1:
        duplicate_groups += 1
        duplicate_games += run_count
    close_to(-1)
    interval_nodes = sum(nodes_by_ply.values())
    return TrieShape(
        games=games,
        plies=plies,
        nodes_by_ply=dict(sorted(nodes_by_ply.items())),
        branching_distribution=dict(sorted(branching.items())),
        terminal_depths=dict(sorted(terminal_depths.items())),
        identical_complete_line_groups=duplicate_groups,
        games_in_identical_complete_lines=duplicate_games,
        games_ending_at_internal_nodes=internal_endings,
        membership_entries=membership_entries,
        interval_nodes=interval_nodes,
        edges=max(0, interval_nodes - 1),
        patricia_removable_nodes=patricia_removable,
    )
