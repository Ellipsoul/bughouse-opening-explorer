"""Low-cardinality startup and first-request measurements for packed readers."""

import json
import os
from pathlib import Path
import resource
import sys
import time

from .service import OpeningReadService


def _peak_rss_bytes(usage):
    return usage.ru_maxrss if sys.platform == "darwin" else usage.ru_maxrss * 1024


def _timed_json(call, *, scaling):
    started = time.perf_counter_ns()
    response = call()
    wall_ms = (time.perf_counter_ns() - started) / 1_000_000
    encoded_bytes = len(
        json.dumps(response, separators=(",", ":"), sort_keys=True).encode()
    )
    measurement = {
        "encoded_bytes": encoded_bytes,
        "scaling": scaling,
        "wall_ms": wall_ms,
    }
    if isinstance(response, dict) and isinstance(response.get("nodes"), list):
        measurement["returned_nodes"] = len(response["nodes"])
    return response, measurement


def measure_first_load(artifact):
    """Measure one fresh reader plus its sequential metadata/root request path."""
    artifact = Path(artifact)
    usage_before = resource.getrusage(resource.RUSAGE_SELF)
    cpu_started = time.process_time_ns()

    with OpeningReadService(artifact) as service:
        version = service.dataset_version
        metadata, first_metadata = _timed_json(
            service.metadata,
            scaling="constant",
        )
        neighborhood_call = lambda: service.neighborhood(
            dataset_version=version,
            anchor_node_id=metadata["root_node_id"],
            anchor_state_id=metadata.get("root_state_id"),
        )
        _first_neighborhood_response, first_neighborhood = _timed_json(
            neighborhood_call,
            scaling="request_budget_bounded",
        )
        _warm_metadata_response, warm_metadata = _timed_json(
            service.metadata,
            scaling="constant",
        )
        _warm_neighborhood_response, warm_neighborhood = _timed_json(
            neighborhood_call,
            scaling="request_budget_bounded",
        )
        startup = service.startup_profile

    usage_after = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "dataset_version": version,
        "process": {
            "cpu_ms": (time.process_time_ns() - cpu_started) / 1_000_000,
            "input_block_bytes": max(0, usage_after.ru_inblock - usage_before.ru_inblock) * 512,
            "major_page_faults": max(0, usage_after.ru_majflt - usage_before.ru_majflt),
            "mapped_virtual_bytes": startup["phases"]["mmap_construction"]["mapped_bytes"],
            "minor_page_faults": max(0, usage_after.ru_minflt - usage_before.ru_minflt),
            "open_files": len(os.listdir("/dev/fd")) if Path("/dev/fd").is_dir() else None,
            "peak_rss_bytes": _peak_rss_bytes(usage_after),
        },
        "requests": {
            "first_metadata": first_metadata,
            "first_neighborhood": first_neighborhood,
            "warm_metadata": warm_metadata,
            "warm_neighborhood": warm_neighborhood,
        },
        "startup": startup,
    }
