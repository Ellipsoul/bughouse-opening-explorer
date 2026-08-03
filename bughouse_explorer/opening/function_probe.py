"""Minimal filesystem and mmap probe for hosted Python function runtimes."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import sys
import threading
import time
import uuid

from .packed import PackedIndex
from .publication import validate_artifact


def _peak_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


class FunctionCompatibilityProbe:
    """Validate once, retain mappings, and report only bounded runtime facts."""

    def __init__(self, artifact, *, scratch_directory="/tmp", bundle_directory=None):
        started = time.perf_counter_ns()
        self.artifact = Path(artifact).resolve()
        self.scratch_directory = Path(scratch_directory).resolve()
        self.bundle_directory = Path(bundle_directory or Path.cwd()).resolve()
        self.scratch_directory.mkdir(parents=True, exist_ok=True)
        validated = validate_artifact(self.artifact)
        self.index = PackedIndex(self.artifact)
        if self.index.manifest["build_id"] != validated.build_id:
            self.index.close()
            raise ValueError("validated build id changed while opening probe artifact")
        self.instance_id = uuid.uuid4().hex
        self.initialization_ms = (time.perf_counter_ns() - started) / 1_000_000
        self.invocation_count = 0
        self._lock = threading.Lock()

    def close(self):
        self.index.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def _scratch_probe(self):
        usage = shutil.disk_usage(self.scratch_directory)
        payload = b"bughouse-opening-function-probe\0" * 32_768
        expected = hashlib.sha256(payload).hexdigest()
        path = self.scratch_directory / f"opening-probe-{self.instance_id}.bin"
        try:
            with path.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            observed = hashlib.sha256(path.read_bytes()).hexdigest()
            return {
                "available_bytes": usage.free,
                "round_trip_bytes": len(payload),
                "round_trip_validated": observed == expected,
                "writable": True,
            }
        finally:
            path.unlink(missing_ok=True)

    def _bundle_write_probe(self):
        path = self.bundle_directory / f".opening-probe-{self.instance_id}"
        created = False
        try:
            with path.open("x") as stream:
                stream.write("probe")
            created = True
            return True
        except OSError:
            return False
        finally:
            if created:
                path.unlink(missing_ok=True)

    def _concurrent_reads(self, count):
        if not 1 <= count <= 64:
            raise ValueError("concurrent_reads must be between 1 and 64")
        node_total = self.index.manifest["nodes"]
        node_ids = [((index + 1) * 104_729) % node_total for index in range(count)]

        def read_node(node_id):
            node = self.index._node(node_id)
            return node_id, node[2], node[3]

        failures = 0
        digest = hashlib.sha256()
        with ThreadPoolExecutor(max_workers=min(count, 16)) as executor:
            futures = [executor.submit(read_node, node_id) for node_id in node_ids]
            for future in futures:
                try:
                    digest.update(repr(future.result()).encode())
                except Exception:
                    failures += 1
        return failures, digest.hexdigest()

    def run(self, *, concurrent_reads=16):
        started = time.perf_counter_ns()
        with self._lock:
            self.invocation_count += 1
            invocation_count = self.invocation_count
        failures, read_digest = self._concurrent_reads(concurrent_reads)
        manifest = self.index.manifest
        component_bytes = sum(record["bytes"] for record in manifest["files"].values())
        return {
            "artifact": {
                "bytes": component_bytes,
                "checksum_validated": True,
                "dataset_version": manifest.get("dataset_version", manifest["build_id"]),
                "format_version": manifest.get("format_version", "packed-prefix-interval-v1"),
                "games": manifest["games"],
                "nodes": manifest["nodes"],
            },
            "bundle": {
                "path": str(self.bundle_directory),
                "readable": os.access(self.artifact, os.R_OK),
                "writable": self._bundle_write_probe(),
            },
            "instance": {
                "id": self.instance_id,
                "initialization_ms": self.initialization_ms,
                "invocation_count": invocation_count,
                "reader_reused": invocation_count > 1,
            },
            "mmap": {
                "concurrent_reads": concurrent_reads,
                "failures": failures,
                "read_digest": read_digest,
            },
            "process": {
                "peak_rss_bytes": _peak_rss_bytes(),
                "probe_elapsed_ms": (time.perf_counter_ns() - started) / 1_000_000,
                "python": sys.version.split()[0],
            },
            "scratch": self._scratch_probe(),
        }


def report_json(probe, *, concurrent_reads=16):
    return json.dumps(
        probe.run(concurrent_reads=concurrent_reads),
        separators=(",", ":"),
        sort_keys=True,
    )
