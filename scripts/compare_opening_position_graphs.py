#!/usr/bin/env python3
"""Compare sampled public behavior between two packed position graphs."""

import argparse
import json
from pathlib import Path
import random

from bughouse_explorer.opening.model import QueryFilter
from bughouse_explorer.opening.position_graph_packed import PackedPositionGraph


BROWSER_GAME_FIELDS = {
    "black_rating",
    "black_result",
    "black_username",
    "provenance_flags",
    "source",
    "url",
    "uuid",
    "white_rating",
    "white_result",
    "white_username",
}


def _sample_ids(count, sample_size, seed):
    if sample_size >= count:
        return range(count)
    values = {0, count - 1}
    generator = random.Random(seed)
    while len(values) < sample_size:
        values.add(generator.randrange(count))
    return sorted(values)


def _browser_game(metadata):
    return {key: metadata[key] for key in BROWSER_GAME_FIELDS}


def _popular_player(graph, seat):
    prefix = f"{seat}\0"
    key = max(
        (key for key in graph.posting_index if key.startswith(prefix)),
        key=lambda value: (graph.posting_index[value]["count"], value),
    )
    return key.split("\0", 1)[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("oracle", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--states", type=int, default=10_000)
    parser.add_argument("--games", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20_260_903)
    arguments = parser.parse_args()
    if arguments.states < 2 or arguments.games < 2:
        parser.error("--states and --games must each be at least 2")

    with PackedPositionGraph(arguments.oracle) as oracle, PackedPositionGraph(
        arguments.candidate
    ) as candidate:
        for field in (
            "build_id",
            "dataset_version",
            "edges",
            "games",
            "positions",
            "root_node_id",
            "root_state_id",
            "states",
        ):
            if candidate.manifest[field] != oracle.manifest[field]:
                raise ValueError(f"manifest mismatch: {field}")

        state_ids = _sample_ids(
            oracle.manifest["states"], arguments.states, arguments.seed
        )
        for state_id in state_ids:
            if candidate.query_state(state_id) != oracle.query_state(state_id):
                raise ValueError(f"unfiltered state mismatch: {state_id}")

        game_ids = _sample_ids(
            oracle.manifest["games"], arguments.games, arguments.seed + 1
        )
        for ordinal in game_ids:
            if candidate.game(ordinal) != _browser_game(oracle.game(ordinal)):
                raise ValueError(f"browser game mismatch: {ordinal}")

        popular_white = _popular_player(oracle, "white")
        popular_black = _popular_player(oracle, "black")
        filters = (
            QueryFilter(white_username=popular_white),
            QueryFilter(black_username=popular_black),
            QueryFilter(
                white_username=popular_white,
                black_username=popular_black,
            ),
        )
        for query_filter in filters:
            state_id = oracle.root_state_id
            if candidate.query_state(state_id, query_filter) != oracle.query_state(
                state_id, query_filter
            ):
                raise ValueError(f"filtered root mismatch: {query_filter!r}")

        print(
            json.dumps(
                {
                    "build_id": candidate.manifest["build_id"],
                    "candidate_format": candidate.manifest["format_version"],
                    "filtered_root_cases": len(filters),
                    "sampled_games": len(game_ids),
                    "sampled_states": len(state_ids),
                },
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
