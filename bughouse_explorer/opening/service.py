"""Experimental bounded read boundary over a validated packed artifact."""

from bisect import bisect_left
import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import heapq
import json
from pathlib import Path
import secrets
import time

from .model import QueryFilter
from .packed import PackedIndex, UINT32
from .position_graph_packed import PackedPositionGraph
from .publication import validate_artifact_profiled


DEFAULT_TARGET_DEPTH = 5
DEFAULT_MAX_NODES = 500
DEFAULT_MAX_ENCODED_BYTES = 256 * 1024
HARD_MAX_NODES = 4_000
HARD_MAX_ENCODED_BYTES = 512 * 1024
HARD_MAX_TARGET_DEPTH = 16


class StaleDatasetVersion(ValueError):
    def __init__(self, requested, expected):
        super().__init__(f"stale dataset version {requested!r}; expected {expected!r}")
        self.requested = requested
        self.expected = expected


class InvalidNodeId(ValueError):
    pass


class BudgetExceeded(ValueError):
    pass


class OpeningReadService:
    """Own one validated, read-only, memory-mapped dataset version."""

    def __init__(self, artifact):
        startup_started = time.perf_counter_ns()
        self.artifact = Path(artifact).resolve()
        validated, phases = validate_artifact_profiled(self.artifact)
        self.graph_mode = validated.format == "packed-position-graph"
        if not self.graph_mode and not validated.format.startswith("packed-sorted"):
            raise ValueError("opening service requires packed sorted postings")
        self.index = (
            PackedPositionGraph(self.artifact)
            if self.graph_mode
            else PackedIndex(self.artifact)
        )
        if self.index.manifest["build_id"] != validated.build_id:
            self.index.close()
            raise ValueError("validated build id changed while opening artifact")
        phases.update(getattr(self.index, "startup_profile", {}))
        self.startup_profile = {
            "phases": phases,
            "total_wall_ms": (time.perf_counter_ns() - startup_started) / 1_000_000,
        }

    def close(self):
        self.index.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def metadata(self):
        manifest = self.index.manifest
        return {
            "adapter_policy": manifest["adapter_policy"],
            "coverage": {
                "accepted_games": manifest["games"],
                "source_fingerprint": manifest["source_fingerprint"],
            },
            "dataset_version": manifest.get(
                "dataset_version", manifest["build_id"]
            ),
            "format_version": manifest.get(
                "format_version", "packed-prefix-interval-v1"
            ),
            "root_node_id": manifest.get("root_node_id", 0),
            **(
                {
                    "replay_policy": manifest["replay_policy"],
                    "root_state_id": manifest["root_state_id"],
                }
                if self.graph_mode
                else {}
            ),
            "terminal_policy": manifest["terminal_policy"],
        }

    @property
    def dataset_version(self):
        return self.index.manifest.get(
            "dataset_version", self.index.manifest["build_id"]
        )

    def _require_version(self, requested):
        if requested != self.dataset_version:
            raise StaleDatasetVersion(requested, self.dataset_version)

    def _node(self, node_id):
        if not isinstance(node_id, int) or not 0 <= node_id < self.index.manifest["nodes"]:
            raise InvalidNodeId(f"invalid node id: {node_id!r}")
        return self.index._node(node_id)

    def _incoming_token(self, node_id, node=None):
        if node_id == 0:
            return None
        node = node or self._node(node_id)
        parent_id = node[0]
        for token, child_id in self.index._children(self._node(parent_id)):
            if child_id == node_id:
                return token
        raise ValueError(f"node {node_id} is not linked from parent {parent_id}")

    def _path(self, node_id):
        path = []
        while True:
            node = self._node(node_id)
            path.append(
                {
                    "move_token": self._incoming_token(node_id, node),
                    "node_id": node_id,
                }
            )
            if node_id == 0:
                break
            node_id = node[0]
        path.reverse()
        return path

    def _normalize_filter(self, query_filter):
        if query_filter is None:
            return None
        if not isinstance(query_filter, QueryFilter):
            raise TypeError("query_filter must be QueryFilter or None")
        values = (query_filter.white_username, query_filter.black_username)
        for value in values:
            if value is not None and (
                not value or len(value) > 64 or any(ord(character) < 32 for character in value)
            ):
                raise ValueError("player filters must contain 1 to 64 printable characters")
        if not any(values):
            return None
        return query_filter

    def neighborhood(
        self,
        *,
        dataset_version,
        anchor_node_id: int,
        anchor_state_id: int | None = None,
        target_forward_depth: int = DEFAULT_TARGET_DEPTH,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_encoded_bytes: int = DEFAULT_MAX_ENCODED_BYTES,
        query_filter: QueryFilter | None = None,
    ):
        started = time.perf_counter_ns()
        self._require_version(dataset_version)
        query_filter = self._normalize_filter(query_filter)
        if not 0 <= target_forward_depth <= HARD_MAX_TARGET_DEPTH:
            raise BudgetExceeded(
                f"target_forward_depth must be between 0 and {HARD_MAX_TARGET_DEPTH}"
            )
        if not 1 <= max_nodes <= HARD_MAX_NODES:
            raise BudgetExceeded(f"max_nodes must be between 1 and {HARD_MAX_NODES}")
        if not 1_024 <= max_encoded_bytes <= HARD_MAX_ENCODED_BYTES:
            raise BudgetExceeded(
                "max_encoded_bytes must be between 1024 and "
                f"{HARD_MAX_ENCODED_BYTES}"
            )

        if self.graph_mode:
            return self._graph_neighborhood(
                started=started,
                anchor_node_id=anchor_node_id,
                anchor_state_id=anchor_state_id,
                target_forward_depth=target_forward_depth,
                max_nodes=max_nodes,
                max_encoded_bytes=max_encoded_bytes,
                query_filter=query_filter,
            )

        anchor = self._node(anchor_node_id)
        records = {anchor_node_id: anchor}
        depths = {anchor_node_id: 0}
        incoming = {anchor_node_id: self._incoming_token(anchor_node_id, anchor)}
        edges = {}
        inclusion_groups = []
        visited_nodes = 1
        budget_exception = False

        immediate = list(self.index._children(anchor))
        for token, child_id in immediate:
            child = self._node(child_id)
            records[child_id] = child
            depths[child_id] = 1
            incoming[child_id] = token
            edges[(anchor_node_id, child_id)] = token
            visited_nodes += 1
        if len(records) > max_nodes:
            budget_exception = True

        candidates = []

        def queue_parent(parent_id):
            parent_depth = depths[parent_id]
            if parent_depth >= target_forward_depth or not records[parent_id][5]:
                return
            support = records[parent_id][3] - records[parent_id][2]
            heapq.heappush(candidates, (-support, parent_id))

        for _token, child_id in immediate:
            queue_parent(child_id)
        if not immediate:
            queue_parent(anchor_node_id)

        while candidates and len(records) < max_nodes:
            _negative_support, parent_id = heapq.heappop(candidates)
            children = [
                (token, child_id)
                for token, child_id in self.index._children(records[parent_id])
                if child_id not in records
            ]
            visited_nodes += len(children)
            if not children or len(records) + len(children) > max_nodes:
                continue
            group = []
            for token, child_id in children:
                child = self._node(child_id)
                records[child_id] = child
                depths[child_id] = depths[parent_id] + 1
                incoming[child_id] = token
                edges[(parent_id, child_id)] = token
                group.append(child_id)
            inclusion_groups.append(group)
            for child_id in group:
                queue_parent(child_id)

        anchor_start, anchor_end = anchor[2], anchor[3]
        selected = None
        if query_filter is not None:
            selected = self.index._selected(query_filter, anchor_start, anchor_end)
        result_cache = {}
        overlay_cache = {}

        def overlay(node_id, node):
            if node_id in overlay_cache:
                return overlay_cache[node_id]
            start, end = node[2], node[3]
            if selected is None:
                support = end - start
                selected_start = selected_end = None
            else:
                selected_start = bisect_left(selected, start)
                selected_end = bisect_left(selected, end)
                support = selected_end - selected_start
            ending_start, ending_total = node[6], node[7]
            actual_endings = 0
            if ending_total:
                for offset in range(ending_start, ending_start + ending_total):
                    ordinal = UINT32.unpack_from(
                        self.index._maps["endings.bin"], offset * UINT32.size
                    )[0]
                    if selected is None or (
                        bisect_left(selected, ordinal) < len(selected)
                        and selected[bisect_left(selected, ordinal)] == ordinal
                    ):
                        actual_endings += 1
            result_counts = {}
            if selected is None:
                for result in self.index.manifest["results"]:
                    count = self.index._posting_count(
                        f"result\0{result}", start, end
                    )
                    if count:
                        result_counts[result] = count
            else:
                for ordinal in selected[selected_start:selected_end]:
                    if ordinal not in result_cache:
                        result_cache[ordinal] = (
                            self.index._game(ordinal)["white_result"] or "unknown"
                        )
                    result = result_cache[ordinal]
                    result_counts[result] = result_counts.get(result, 0) + 1
            sole_ordinal = None
            if support == 1:
                sole_ordinal = node[8] if selected is None else selected[selected_start]
            value = {
                "actual_ending_count": actual_endings,
                "results": dict(sorted(result_counts.items())),
                "sole_game_ordinal": sole_ordinal,
                "support": support,
            }
            overlay_cache[node_id] = value
            return value

        def assemble(included_ids):
            included_child_counts = {node_id: 0 for node_id in included_ids}
            for parent_id, child_id in edges:
                if parent_id in included_ids and child_id in included_ids:
                    included_child_counts[parent_id] += 1
            structural_nodes = []
            overlays = {}
            frontiers = []
            for node_id in sorted(included_ids):
                node = records[node_id]
                child_count = node[5]
                structural_nodes.append(
                    {
                        "child_count": child_count,
                        "id": node_id,
                        "interval_end": node[3],
                        "interval_start": node[2],
                        "move_token": incoming[node_id],
                        "parent_id": None if node[0] < 0 else node[0],
                        "ply": node[1],
                    }
                )
                overlays[str(node_id)] = overlay(node_id, node)
                if child_count > included_child_counts[node_id]:
                    frontiers.append(
                        {
                            "has_more": True,
                            "node_id": node_id,
                            "reason": (
                                "target_depth"
                                if depths[node_id] >= target_forward_depth
                                else "budget"
                            ),
                        }
                    )
            flat_edges = [
                {
                    "child_id": child_id,
                    "move_token": token,
                    "parent_id": parent_id,
                }
                for (parent_id, child_id), token in sorted(
                    edges.items(), key=lambda item: (item[0][0], item[1], item[0][1])
                )
                if parent_id in included_ids and child_id in included_ids
            ]
            return {
                "anchor_node_id": anchor_node_id,
                "dataset_version": self.dataset_version,
                "edges": flat_edges,
                "filter": (
                    None
                    if query_filter is None
                    else {
                        "black_username": query_filter.black_username,
                        "white_username": query_filter.white_username,
                    }
                ),
                "frontiers": frontiers,
                "nodes": structural_nodes,
                "overlays": overlays,
                "path": self._path(anchor_node_id),
                "target_forward_depth": target_forward_depth,
            }

        full_ids = set(records)
        response = assemble(full_ids)
        encoded_bytes = len(
            json.dumps(response, separators=(",", ":"), sort_keys=True).encode()
        )
        required = {anchor_node_id, *(child_id for _token, child_id in immediate)}
        response_budget = max(0, max_encoded_bytes - 512)
        if encoded_bytes > response_budget:
            required_response = assemble(required)
            required_bytes = len(
                json.dumps(
                    required_response, separators=(",", ":"), sort_keys=True
                ).encode()
            )
            if required_bytes > response_budget:
                budget_exception = True
                response = required_response
                encoded_bytes = required_bytes
            else:
                low = 0
                high = len(inclusion_groups)
                best_response = required_response
                best_bytes = required_bytes
                while low <= high:
                    middle = (low + high) // 2
                    candidate = assemble(
                        required
                        | {
                            node_id
                            for group in inclusion_groups[:middle]
                            for node_id in group
                        }
                    )
                    candidate_bytes = len(
                        json.dumps(
                            candidate, separators=(",", ":"), sort_keys=True
                        ).encode()
                    )
                    if candidate_bytes <= response_budget:
                        best_response = candidate
                        best_bytes = candidate_bytes
                        low = middle + 1
                    else:
                        high = middle - 1
                response = best_response
                encoded_bytes = best_bytes

        response["instrumentation"] = {
            "budget_exception": budget_exception,
            "encoded_bytes": encoded_bytes,
            "elapsed_microseconds": (time.perf_counter_ns() - started) // 1_000,
            "returned_edges": len(response["edges"]),
            "returned_nodes": len(response["nodes"]),
            "visited_nodes": visited_nodes,
        }
        response["instrumentation"]["encoded_bytes"] = len(
            json.dumps(response, separators=(",", ":"), sort_keys=True).encode()
        )
        return response

    def _graph_neighborhood(
        self,
        *,
        started,
        anchor_node_id,
        anchor_state_id,
        target_forward_depth,
        max_nodes,
        max_encoded_bytes,
        query_filter,
    ):
        """Return a cycle-safe, state-qualified graph neighborhood."""
        if anchor_state_id is None:
            if anchor_node_id != self.index.root_position_id:
                raise InvalidNodeId("non-root graph requests require anchor_state_id")
            anchor_state_id = self.index.root_state_id
        try:
            anchor_state = self.index.state_structure(anchor_state_id)
            anchor_position = self.index.position_structure(anchor_node_id)
        except KeyError as error:
            raise InvalidNodeId(f"invalid graph anchor: {error.args[0]!r}") from error
        if anchor_state["node_id"] != anchor_position["id"]:
            raise InvalidNodeId(
                f"state {anchor_state_id} does not belong to node {anchor_node_id}"
            )

        selected = self.index.selected_games(query_filter)
        states = {anchor_state_id: anchor_state}
        nodes = {anchor_node_id: anchor_position}
        depths = {anchor_state_id: 0}
        edges = {}
        frontiers = set()
        expanded_parents = []
        expanded_edges = {}
        queue = [anchor_state_id]
        visited_states = 0
        budget_exception = False

        while queue:
            parent_state_id = queue.pop(0)
            parent_depth = depths[parent_state_id]
            visited_states += 1
            outgoing = self.index.outgoing_edges(parent_state_id)
            if parent_depth >= target_forward_depth:
                if outgoing:
                    frontiers.add(parent_state_id)
                continue
            new_state_ids = {
                edge["child_state_id"]
                for edge in outgoing
                if edge["child_state_id"] not in states
            }
            if len(states) + len(new_state_ids) > max_nodes:
                if parent_state_id == anchor_state_id:
                    raise BudgetExceeded(
                        "the anchor's atomic graph neighborhood exceeds max_nodes"
                    )
                frontiers.add(parent_state_id)
                budget_exception = True
                continue
            expanded_parents.append(parent_state_id)
            expanded_edges[parent_state_id] = tuple(edge["id"] for edge in outgoing)
            for edge in outgoing:
                edges[edge["id"]] = edge
                child_state_id = edge["child_state_id"]
                child_node_id = edge["child_id"]
                if child_node_id not in nodes:
                    nodes[child_node_id] = self.index.position_structure(child_node_id)
                if child_state_id not in states:
                    states[child_state_id] = self.index.state_structure(child_state_id)
                    depths[child_state_id] = parent_depth + 1
                    queue.append(child_state_id)

        game_cache = {}

        def result_counts(ordinals, wins=0, draws=0, losses=0):
            if selected is None:
                return {
                    name: count
                    for name, count in (("draw", draws), ("loss", losses), ("win", wins))
                    if count
                }
            counts = {}
            draw_codes = {
                "50move",
                "agreed",
                "insufficient",
                "repetition",
                "stalemate",
                "timevsinsufficient",
                "timevsinsufficientmaterial",
            }
            for ordinal in ordinals:
                metadata = game_cache.get(ordinal)
                if metadata is None:
                    metadata = self.index.game(ordinal)
                    game_cache[ordinal] = metadata
                result = (
                    "win"
                    if metadata["white_result"] == "win"
                    else "draw"
                    if metadata["white_result"] in draw_codes
                    or metadata["black_result"] in draw_codes
                    else "loss"
                )
                counts[result] = counts.get(result, 0) + 1
            return dict(sorted(counts.items()))

        node_overlays = {}
        for node_id, node in nodes.items():
            support = (
                node["support"]
                if selected is None
                else len(self.index.matching_position_games(node_id, selected))
            )
            node_overlays[str(node_id)] = {"support": support}

        state_overlays = {}
        for state_id, state in states.items():
            if selected is None:
                matches = ()
                support = state["_game_count"]
                actual_ending_count = state["_ending_count"]
                sole_game_ordinal = (
                    self.index._membership(state["_game_start"], 1).value(0)
                    if support == 1
                    else None
                )
            else:
                matches = self.index.matching_state_games(state_id, selected)
                ending_matches = self.index.matching_ending_games(state_id, selected)
                support = len(matches)
                actual_ending_count = len(ending_matches)
                sole_game_ordinal = matches[0] if support == 1 else None
            state_overlays[str(state_id)] = {
                "actual_ending_count": actual_ending_count,
                "results": result_counts(
                    matches, state["_wins"], state["_draws"], state["_losses"]
                ),
                "sole_game_ordinal": sole_game_ordinal,
                "support": support,
            }

        edge_overlays = {}
        for edge_id, edge in edges.items():
            if selected is None:
                matches = ()
                support = edge["_game_count"]
                sole_game_ordinal = (
                    self.index._membership(edge["_game_start"], 1).value(0)
                    if support == 1
                    else None
                )
            else:
                matches = self.index.matching_edge_games(edge_id, selected)
                support = len(matches)
                sole_game_ordinal = matches[0] if support == 1 else None
            edge_overlays[str(edge_id)] = {
                "results": result_counts(
                    matches, edge["_wins"], edge["_draws"], edge["_losses"]
                ),
                "sole_game_ordinal": sole_game_ordinal,
                "support": support,
            }

        def assemble(parent_limit):
            included_states = {anchor_state_id}
            included_edges = set()
            included_parents = set()
            for parent_state_id in expanded_parents[:parent_limit]:
                if parent_state_id not in included_states:
                    continue
                included_parents.add(parent_state_id)
                for edge_id in expanded_edges[parent_state_id]:
                    included_edges.add(edge_id)
                    included_states.add(edges[edge_id]["child_state_id"])
            included_nodes = {states[state_id]["node_id"] for state_id in included_states}
            response_frontiers = set(frontiers) & included_states
            for state_id in included_states:
                if states[state_id]["outgoing_count"] and state_id not in included_parents:
                    response_frontiers.add(state_id)
            return {
                "anchor_node_id": anchor_node_id,
                "anchor_state_id": anchor_state_id,
                "dataset_version": self.dataset_version,
                "edge_overlays": {
                    str(edge_id): edge_overlays[str(edge_id)]
                    for edge_id in sorted(included_edges)
                },
                "edges": [
                    {
                        key: value
                        for key, value in edges[edge_id].items()
                        if not key.startswith("_")
                    }
                    for edge_id in sorted(included_edges)
                ],
                "filter": (
                    None
                    if query_filter is None
                    else {
                        "black_username": query_filter.black_username,
                        "white_username": query_filter.white_username,
                    }
                ),
                "frontiers": [
                    {
                        "has_more": True,
                        "node_id": states[state_id]["node_id"],
                        "reason": (
                            "target_depth"
                            if depths[state_id] >= target_forward_depth
                            else "budget"
                        ),
                        "state_id": state_id,
                    }
                    for state_id in sorted(response_frontiers)
                ],
                "node_overlays": {
                    str(node_id): node_overlays[str(node_id)]
                    for node_id in sorted(included_nodes)
                },
                "nodes": [
                    {
                        key: value
                        for key, value in nodes[node_id].items()
                        if not key.startswith("_")
                    }
                    for node_id in sorted(included_nodes)
                ],
                "state_overlays": {
                    str(state_id): state_overlays[str(state_id)]
                    for state_id in sorted(included_states)
                },
                "states": [
                    {
                        key: value
                        for key, value in states[state_id].items()
                        if not key.startswith("_")
                    }
                    for state_id in sorted(included_states)
                ],
                "target_forward_depth": target_forward_depth,
            }

        response = assemble(len(expanded_parents))
        encoded_bytes = len(json.dumps(response, separators=(",", ":"), sort_keys=True).encode())
        response_budget = max(0, max_encoded_bytes - 768)
        if encoded_bytes > response_budget:
            required_parents = 1 if expanded_parents and expanded_parents[0] == anchor_state_id else 0
            required_response = assemble(required_parents)
            required_bytes = len(
                json.dumps(required_response, separators=(",", ":"), sort_keys=True).encode()
            )
            if required_bytes > response_budget:
                raise BudgetExceeded(
                    "the anchor's atomic graph neighborhood exceeds max_encoded_bytes"
                )
            low = required_parents
            high = len(expanded_parents)
            response = required_response
            encoded_bytes = required_bytes
            budget_exception = True
            while low <= high:
                middle = (low + high) // 2
                candidate = assemble(middle)
                candidate_bytes = len(
                    json.dumps(candidate, separators=(",", ":"), sort_keys=True).encode()
                )
                if candidate_bytes <= response_budget:
                    response = candidate
                    encoded_bytes = candidate_bytes
                    low = middle + 1
                else:
                    high = middle - 1
        response["instrumentation"] = {
            "budget_exception": budget_exception,
            "elapsed_microseconds": (time.perf_counter_ns() - started) // 1_000,
            "encoded_bytes": 0,
            "returned_edges": len(response["edges"]),
            "returned_nodes": len(response["nodes"]),
            "returned_states": len(response["states"]),
            "visited_nodes": visited_states,
        }
        response["instrumentation"]["encoded_bytes"] = len(
            json.dumps(response, separators=(",", ":"), sort_keys=True).encode()
        )
        return response

    def game_examples(
        self,
        *,
        dataset_version,
        node_id: int,
        limit: int = 6,
        query_filter: QueryFilter | None = None,
    ):
        self._require_version(dataset_version)
        if self.graph_mode:
            raise ValueError(
                "node game examples are ambiguous for position graphs; use an edge id"
            )
        if not 1 <= limit <= 20:
            raise BudgetExceeded("game example limit must be between 1 and 20")
        query_filter = self._normalize_filter(query_filter)
        node = self._node(node_id)
        start, end = node[2], node[3]
        selected = (
            tuple(range(start, end))
            if query_filter is None
            else self.index._selected(query_filter, start, end)
        )
        selected_set = set(selected)
        ending_ordinals = []
        for offset in range(node[6], node[6] + node[7]):
            ordinal = UINT32.unpack_from(
                self.index._maps["endings.bin"], offset * UINT32.size
            )[0]
            if ordinal in selected_set:
                ending_ordinals.append(ordinal)
        ending_set = set(ending_ordinals)
        examples = ending_ordinals + [
            ordinal for ordinal in selected if ordinal not in ending_set
        ]
        games = []
        for ordinal in examples[:limit]:
            metadata = self.index._game(ordinal)
            metadata["actual_ending"] = ordinal in ending_set
            metadata["ordinal"] = ordinal
            games.append(metadata)
        return {
            "actual_ending_count": len(ending_ordinals),
            "dataset_version": self.dataset_version,
            "games": games,
            "limit": limit,
            "node_id": node_id,
            "total_matching": len(selected),
        }

    def edge_game_examples(
        self,
        *,
        dataset_version,
        edge_id: int,
        limit: int = 6,
        query_filter: QueryFilter | None = None,
    ):
        self._require_version(dataset_version)
        if not self.graph_mode:
            raise ValueError("edge examples require a position-graph artifact")
        if not 1 <= limit <= 20:
            raise BudgetExceeded("game example limit must be between 1 and 20")
        query_filter = self._normalize_filter(query_filter)
        try:
            selected = self.index.selected_games(query_filter)
            edge = self.index._edge(edge_id)
            edge_posting = self.index._membership(edge[5], edge[6])
            if selected is None:
                total_matching = edge[6]
                examples = tuple(
                    edge_posting.value(index)
                    for index in range(min(limit, total_matching))
                )
                child_state = self.index._state(edge[1])
                ending_posting = self.index._membership(child_state[5], child_state[6])
                ending_set = {
                    ending_posting.value(index)
                    for index in range(ending_posting.count)
                    if edge_posting.contains(ending_posting.value(index))
                }
                actual_ending_count = len(ending_set)
            else:
                matches = self.index.matching_edge_games(edge_id, selected)
                total_matching = len(matches)
                examples = matches[:limit]
                ending_set = set(
                    self.index.matching_ending_games(edge[1], selected)
                )
                actual_ending_count = sum(
                    ordinal in ending_set for ordinal in matches
                )
        except KeyError as error:
            raise InvalidNodeId(f"invalid edge id: {edge_id!r}") from error
        games = []
        for ordinal in examples:
            metadata = self.index.game(ordinal)
            metadata["actual_ending"] = ordinal in ending_set
            metadata["ordinal"] = ordinal
            games.append(metadata)
        return {
            "actual_ending_count": actual_ending_count,
            "dataset_version": self.dataset_version,
            "edge_id": edge_id,
            "games": games,
            "limit": limit,
            "total_matching": total_matching,
        }

    def search_players(self, *, dataset_version, prefix: str, limit: int = 10):
        self._require_version(dataset_version)
        normalized = prefix.strip().casefold()
        if not normalized or len(normalized) > 32 or any(
            ord(character) < 32 for character in normalized
        ):
            raise ValueError("player prefix must contain 1 to 32 printable characters")
        if not 1 <= limit <= 20:
            raise BudgetExceeded("player search limit must be between 1 and 20")

        by_username = {}
        for seat in ("black", "white"):
            seat_prefix = f"{seat}\0"
            matched = 0
            for key, record in self.index.posting_index.items():
                if not key.startswith(seat_prefix):
                    continue
                username = key[len(seat_prefix) :]
                if username.startswith(normalized):
                    counts = by_username.setdefault(
                        username, {"black_games": 0, "white_games": 0}
                    )
                    counts[f"{seat}_games"] = record["count"]
                    matched += 1
                    if matched > limit:
                        break
                elif matched and username > normalized:
                    break
        ordered = sorted(by_username)
        players = [
            {"username": username, **by_username[username]}
            for username in ordered[:limit]
        ]
        return {
            "dataset_version": self.dataset_version,
            "limit": limit,
            "players": players,
            "prefix": normalized,
            "truncated": len(ordered) > limit,
        }


def create_opening_service(
    artifact,
    *,
    allowed_origins=("http://127.0.0.1:3000", "http://localhost:3000"),
    bearer_token=None,
    max_concurrency=8,
    concurrency_wait_seconds=0.05,
):
    """Create a bounded HTTP app after validating the immutable artifact."""
    from fastapi import FastAPI, Query, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, Response

    if not isinstance(max_concurrency, int) or max_concurrency < 1:
        raise ValueError("max_concurrency must be a positive integer")
    if not 0 < concurrency_wait_seconds <= 5:
        raise ValueError("concurrency_wait_seconds must be between 0 and 5")
    if bearer_token is not None and not bearer_token:
        raise ValueError("bearer_token must be non-empty when configured")

    reader = OpeningReadService(artifact)
    semaphore = asyncio.Semaphore(max_concurrency)

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            reader.close()

    app = FastAPI(
        title="Bughouse Opening Explorer Read Boundary",
        version="experimental-v1",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_methods=["GET"],
        allow_headers=["authorization", "if-none-match"],
    )

    @app.middleware("http")
    async def protect_and_bound(request: Request, call_next):
        if request.url.path == "/healthz":
            return await call_next(request)
        if bearer_token is not None:
            supplied = request.headers.get("authorization", "")
            expected = f"Bearer {bearer_token}"
            if not secrets.compare_digest(supplied, expected):
                return JSONResponse(
                    status_code=401,
                    content={"code": "unauthorized"},
                    headers={
                        "cache-control": "no-store",
                        "www-authenticate": "Bearer",
                    },
                )
        try:
            await asyncio.wait_for(
                semaphore.acquire(), timeout=concurrency_wait_seconds
            )
        except TimeoutError:
            return JSONResponse(
                status_code=503,
                content={"code": "concurrency_limit"},
                headers={"cache-control": "no-store", "retry-after": "1"},
            )
        try:
            return await call_next(request)
        finally:
            semaphore.release()

    def versioned_response(request, payload, *, immutable=True):
        timing = None
        if isinstance(payload, dict) and isinstance(
            payload.get("instrumentation"), dict
        ):
            payload = dict(payload)
            payload["instrumentation"] = dict(payload["instrumentation"])
            timing = payload["instrumentation"].get("elapsed_microseconds")
            payload["instrumentation"]["elapsed_microseconds"] = 0
            payload["instrumentation"]["encoded_bytes"] = 0
            for _iteration in range(3):
                body = json.dumps(
                    payload, separators=(",", ":"), sort_keys=True
                ).encode()
                payload["instrumentation"]["encoded_bytes"] = len(body)
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        etag = f'"{hashlib.sha256(body).hexdigest()}"'
        headers = {
            "cache-control": (
                "private, max-age=31536000, immutable"
                if immutable
                else "private, no-cache"
            ),
            "etag": etag,
        }
        if timing is not None:
            headers["server-timing"] = f"reader;dur={timing / 1_000:.3f}"
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(
            content=body,
            media_type="application/json",
            headers=headers,
        )

    @app.get("/healthz")
    def health():
        return JSONResponse(
            content={"status": "alive"}, headers={"cache-control": "no-store"}
        )

    @app.get("/readyz")
    def readiness(request: Request):
        return versioned_response(
            request, {"status": "ready", **reader.metadata()}, immutable=False
        )

    @app.exception_handler(StaleDatasetVersion)
    async def stale_handler(_request: Request, error: StaleDatasetVersion):
        return JSONResponse(
            status_code=409,
            content={
                "code": "stale_dataset_version",
                "dataset_version": error.expected,
                "detail": str(error),
            },
        )

    @app.exception_handler(InvalidNodeId)
    async def node_handler(_request: Request, error: InvalidNodeId):
        return JSONResponse(
            status_code=404,
            content={
                "code": "invalid_node_id",
                "dataset_version": reader.dataset_version,
                "detail": str(error),
            },
        )

    @app.exception_handler(BudgetExceeded)
    async def budget_handler(_request: Request, error: BudgetExceeded):
        return JSONResponse(
            status_code=422,
            content={
                "code": "budget_exceeded",
                "dataset_version": reader.dataset_version,
                "detail": str(error),
            },
        )

    @app.exception_handler(ValueError)
    async def invalid_request_handler(_request: Request, error: ValueError):
        return JSONResponse(
            status_code=422,
            content={
                "code": "invalid_request",
                "dataset_version": reader.dataset_version,
                "detail": str(error),
            },
        )

    def query_filter(white, black):
        return (
            QueryFilter(white_username=white, black_username=black)
            if white is not None or black is not None
            else None
        )

    @app.get("/api/meta")
    def metadata(request: Request):
        return versioned_response(request, reader.metadata(), immutable=False)

    @app.get("/api/nodes/{node_id}/neighborhood")
    def neighborhood(
        request: Request,
        node_id: int,
        dataset_version: str,
        state_id: int | None = None,
        target_forward_depth: int = DEFAULT_TARGET_DEPTH,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_encoded_bytes: int = DEFAULT_MAX_ENCODED_BYTES,
        white: str | None = None,
        black: str | None = None,
    ):
        return versioned_response(
            request,
            reader.neighborhood(
                dataset_version=dataset_version,
                anchor_node_id=node_id,
                anchor_state_id=state_id,
                target_forward_depth=target_forward_depth,
                max_nodes=max_nodes,
                max_encoded_bytes=max_encoded_bytes,
                query_filter=query_filter(white, black),
            ),
        )

    @app.get("/api/edges/{edge_id}/games")
    def edge_games(
        request: Request,
        edge_id: int,
        dataset_version: str,
        limit: int = 6,
        white: str | None = None,
        black: str | None = None,
    ):
        return versioned_response(
            request,
            reader.edge_game_examples(
                dataset_version=dataset_version,
                edge_id=edge_id,
                limit=limit,
                query_filter=query_filter(white, black),
            ),
        )

    @app.get("/api/nodes/{node_id}/games")
    def games(
        request: Request,
        node_id: int,
        dataset_version: str,
        limit: int = 6,
        white: str | None = None,
        black: str | None = None,
    ):
        return versioned_response(
            request,
            reader.game_examples(
                dataset_version=dataset_version,
                node_id=node_id,
                limit=limit,
                query_filter=query_filter(white, black),
            ),
        )

    @app.get("/api/players")
    def players(
        request: Request,
        dataset_version: str,
        prefix: str = Query(min_length=1, max_length=32),
        limit: int = 10,
    ):
        return versioned_response(
            request,
            reader.search_players(
                dataset_version=dataset_version,
                prefix=prefix,
                limit=limit,
            ),
        )

    return app


def main():
    parser = argparse.ArgumentParser(
        description="Serve one validated packed opening artifact on loopback only."
    )
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65_535:
        parser.error("--port must be between 1 and 65535")
    import uvicorn

    uvicorn.run(
        create_opening_service(args.artifact),
        host="127.0.0.1",
        port=args.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
