#!/usr/bin/env python3
"""Build and benchmark one opening-index candidate on a deterministic sample."""

import argparse
from collections import Counter
from dataclasses import asdict
import json
import os
from pathlib import Path
import random
import resource
import sqlite3
import statistics
import time

from bughouse_explorer.opening.adapter import CrawlerSnapshotAdapter, SnapshotSelection
from bughouse_explorer.opening.model import PrefixNotFound, QueryFilter
from bughouse_explorer.opening.packed import PackedIndex, build_packed_index
from bughouse_explorer.opening.publication import publish_version, validate_artifact
from bughouse_explorer.opening.relational import RelationalIndex, build_relational_index
from bughouse_explorer.opening.shape import measure_trie_shape
from bughouse_explorer.opening.trie import prepare_trie
from bughouse_explorer.tcn import _T


def _tree_bytes(path):
    if path.is_file():
        return path.stat().st_size
    return sum(candidate.stat().st_size for candidate in path.rglob("*") if candidate.is_file())


def _percentiles(values):
    ordered = sorted(values)

    def percentile(value):
        return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * value))]

    return {
        "p50_ms": statistics.median(ordered),
        "p95_ms": percentile(0.95),
        "p99_ms": percentile(0.99),
    }


def _prefix(prepared, node_id):
    tokens = []
    while node_id:
        node = prepared.nodes[node_id]
        tokens.append(node.move_token)
        node_id = node.parent_id
    return tuple(reversed(tokens))


def _query_corpus(games, source_fingerprint):
    prepared = prepare_trie(games, source_fingerprint=source_fingerprint)
    nodes = prepared.nodes
    mid_candidates = [node for node in nodes if node.ply == 6]
    mid = max(mid_candidates, key=lambda node: node.interval_end - node.interval_start)
    deep = max(
        (node for node in nodes if node.interval_end - node.interval_start > 1),
        key=lambda node: node.ply,
    )
    terminal = min(
        (node for node in nodes if node.terminal_ordinal is not None and node.ply > 0),
        key=lambda node: (abs(node.ply - 12), node.id),
    )
    root_tokens = {nodes[child].move_token for child in nodes[0].children}
    missing = next(
        left + right
        for left in dict.fromkeys(_T)
        for right in dict.fromkeys(_T)
        if left + right not in root_tokens
    )

    white_counts = Counter(game.white_username for game in games)
    black_counts = Counter(game.black_username for game in games)
    pair_counts = Counter((game.white_username, game.black_username) for game in games)
    prolific_white = max(white_counts, key=lambda key: (white_counts[key], key))
    prolific_black = max(black_counts, key=lambda key: (black_counts[key], key))
    exact_pair = max(pair_counts, key=lambda key: (pair_counts[key], key))
    sparse_white = min(key for key, count in white_counts.items() if count == 1)
    sparse_black = min(key for key, count in black_counts.items() if count == 1)
    return [
        {"name": "root", "prefix": ()},
        {"name": "mid", "prefix": _prefix(prepared, mid.id)},
        {"name": "deep", "prefix": _prefix(prepared, deep.id)},
        {"name": "missing", "prefix": (missing,), "missing": True},
        {"name": "global_support_one", "prefix": _prefix(prepared, terminal.id)},
        {"name": "white_prolific", "prefix": (), "white": prolific_white},
        {"name": "black_prolific", "prefix": (), "black": prolific_black},
        {
            "name": "exact_pairing",
            "prefix": (),
            "white": exact_pair[0],
            "black": exact_pair[1],
        },
        {"name": "white_filtered_support_one", "prefix": (), "white": sparse_white},
        {"name": "black_filtered_support_one", "prefix": (), "black": sparse_black},
    ]


def _execute(index, specification):
    query_filter = None
    if specification.get("white") or specification.get("black"):
        query_filter = QueryFilter(
            white_username=specification.get("white"),
            black_username=specification.get("black"),
        )
    try:
        response = index.query(specification["prefix"], query_filter)
        payload = asdict(response)
    except PrefixNotFound:
        payload = {"error": "prefix_not_found", "prefix": specification["prefix"]}
    return len(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())


def _benchmark_queries(index_type, artifact, specifications, warm_repeats, cold_repeats):
    startup = []
    for _ in range(cold_repeats):
        started = time.perf_counter_ns()
        index = index_type(artifact)
        index.close()
        startup.append((time.perf_counter_ns() - started) / 1_000_000)

    cold = {specification["name"]: [] for specification in specifications}
    response_bytes = {}
    for specification in specifications:
        for _ in range(cold_repeats):
            started = time.perf_counter_ns()
            with index_type(artifact) as index:
                response_bytes[specification["name"]] = _execute(index, specification)
            cold[specification["name"]].append(
                (time.perf_counter_ns() - started) / 1_000_000
            )

    warm = {specification["name"]: [] for specification in specifications}
    order = specifications * warm_repeats
    random.Random(20260803).shuffle(order)
    with index_type(artifact) as index:
        for specification in specifications:
            _execute(index, specification)
        for specification in order:
            started = time.perf_counter_ns()
            _execute(index, specification)
            warm[specification["name"]].append(
                (time.perf_counter_ns() - started) / 1_000_000
            )
    return {
        "startup": _percentiles(startup),
        "cold_open_per_query": {key: _percentiles(values) for key, values in cold.items()},
        "warm": {key: _percentiles(values) for key, values in warm.items()},
        "response_bytes": response_bytes,
        "cold_definition": "new reader per query; OS page cache not forcibly dropped",
    }


def _relational_components(path):
    uri = f"file:{path.resolve()}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        counts = {
            name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in ("games", "nodes", "edges", "membership", "endings", "node_results")
        }
        try:
            sizes = dict(
                connection.execute(
                    "SELECT name, SUM(pgsize) FROM dbstat GROUP BY name ORDER BY name"
                )
            )
        except sqlite3.OperationalError:
            sizes = {"sqlite_file": path.stat().st_size}
    return {"counts": counts, "component_bytes": sizes}


def _packed_components(path):
    manifest = json.loads((path / "manifest.json").read_text())
    postings = json.loads((path / "postings.json").read_text())
    seat_entries = sum(
        record["count"]
        for key, record in postings.items()
        if key.startswith("white\0") or key.startswith("black\0")
    )
    result_entries = sum(
        record["count"] for key, record in postings.items() if key.startswith("result\0")
    )
    return {
        "counts": {
            "games": manifest["games"],
            "nodes": manifest["nodes"],
            "edges": manifest["edges"],
            "membership": 0,
            "seat_posting_entries": seat_entries,
            "result_posting_entries": result_entries,
        },
        "component_bytes": {name: record["bytes"] for name, record in manifest["files"].items()},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--candidate",
        choices=("relational", "packed-sorted", "packed-bitmap"),
        required=True,
    )
    parser.add_argument("--sample-modulus", type=int, default=71)
    parser.add_argument("--warm-repeats", type=int, default=200)
    parser.add_argument("--cold-repeats", type=int, default=20)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    source_fingerprint = (
        "sha256:04b5694a288f1b0a966524090e991d70aa695096531933710a0a17f25bb5a5ac;"
        f"rowid-mod-{args.sample_modulus}-0"
    )

    adapter_started = time.perf_counter()
    outcomes = list(
        CrawlerSnapshotAdapter(args.snapshot).iter_outcomes(
            SnapshotSelection(args.sample_modulus, 0)
        )
    )
    games = [outcome.game for outcome in outcomes if outcome.game is not None]
    adapter_seconds = time.perf_counter() - adapter_started
    shape = measure_trie_shape(games)

    if args.candidate == "relational":
        artifact = args.output / "index.sqlite3"
        builder = build_relational_index
        index_type = RelationalIndex
        builder_kwargs = {}
    else:
        artifact = args.output / "index"
        builder = build_packed_index
        index_type = PackedIndex
        builder_kwargs = {"postings": args.candidate.removeprefix("packed-")}

    before_io = resource.getrusage(resource.RUSAGE_SELF).ru_oublock
    build_started = time.perf_counter()
    build_id = builder(
        games, artifact, source_fingerprint=source_fingerprint, **builder_kwargs
    )
    build_seconds = time.perf_counter() - build_started
    write_bytes_estimate = max(
        0, (resource.getrusage(resource.RUSAGE_SELF).ru_oublock - before_io) * 512
    )
    validation_started = time.perf_counter()
    validated = validate_artifact(artifact)
    validation_seconds = time.perf_counter() - validation_started
    pointer = args.output / "current.json"
    publication_started = time.perf_counter()
    publish_version(artifact, pointer)
    publication_seconds = time.perf_counter() - publication_started

    specifications = _query_corpus(games, source_fingerprint)
    query_metrics = _benchmark_queries(
        index_type,
        artifact,
        specifications,
        args.warm_repeats,
        args.cold_repeats,
    )
    final_bytes = _tree_bytes(artifact)
    components = (
        _relational_components(artifact)
        if args.candidate == "relational"
        else _packed_components(artifact)
    )
    usage = resource.getrusage(resource.RUSAGE_SELF)
    payload = {
        "accepted_games": len(games),
        "adapter_seconds": adapter_seconds,
        "build_id": build_id,
        "build_seconds": build_seconds,
        "candidate": args.candidate,
        "components": components,
        "deterministic_input": source_fingerprint,
        "final_bytes": final_bytes,
        "games_per_second": len(games) / build_seconds,
        "peak_rss_bytes": usage.ru_maxrss,
        "plies": shape.plies,
        "plies_per_second": shape.plies / build_seconds,
        "publication_seconds": publication_seconds,
        "queries": query_metrics,
        "query_corpus": specifications,
        "sample_modulus": args.sample_modulus,
        "shape": asdict(shape),
        "skipped": dict(
            Counter(outcome.skip_reason for outcome in outcomes if outcome.skip_reason)
        ),
        "validated_build_id": validated.build_id,
        "validation_seconds": validation_seconds,
        "write_amplification_estimate": (
            write_bytes_estimate / final_bytes if final_bytes else 0
        ),
        "write_bytes_estimate": write_bytes_estimate,
        "write_measurement": "ru_oublock * 512; excludes unreported filesystem/cache effects",
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.result:
        args.result.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
