"""Portable per-process I/O counters for build amplification measurements."""

import ctypes
from dataclasses import dataclass
import os
from pathlib import Path
import resource
import sys


@dataclass(frozen=True)
class ProcessIoSnapshot:
    logical_write_bytes: int
    method: str
    physical_read_bytes: int
    physical_write_bytes: int
    reliable: bool


def _darwin_snapshot():
    names = [
        "ri_user_time", "ri_system_time", "ri_pkg_idle_wkups",
        "ri_interrupt_wkups", "ri_pageins", "ri_wired_size",
        "ri_resident_size", "ri_phys_footprint", "ri_proc_start_abstime",
        "ri_proc_exit_abstime", "ri_child_user_time", "ri_child_system_time",
        "ri_child_pkg_idle_wkups", "ri_child_interrupt_wkups",
        "ri_child_pageins", "ri_child_elapsed_abstime", "ri_diskio_bytesread",
        "ri_diskio_byteswritten", "ri_cpu_time_qos_default",
        "ri_cpu_time_qos_maintenance", "ri_cpu_time_qos_background",
        "ri_cpu_time_qos_utility", "ri_cpu_time_qos_legacy",
        "ri_cpu_time_qos_user_initiated", "ri_cpu_time_qos_user_interactive",
        "ri_billed_system_time", "ri_serviced_system_time", "ri_logical_writes",
    ]

    class RusageInfoV4(ctypes.Structure):
        _fields_ = (
            [("ri_uuid", ctypes.c_uint8 * 16)]
            + [(name, ctypes.c_uint64) for name in names]
            + [("remaining_v4_fields", ctypes.c_uint64 * 7)]
        )

    info = RusageInfoV4()
    library = ctypes.CDLL("/usr/lib/libproc.dylib")
    library.proc_pid_rusage.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.c_void_p)
    library.proc_pid_rusage.restype = ctypes.c_int
    if library.proc_pid_rusage(os.getpid(), 4, ctypes.byref(info)) != 0:
        return None
    return ProcessIoSnapshot(
        logical_write_bytes=info.ri_logical_writes,
        method="darwin-proc-pid-rusage-v4",
        physical_read_bytes=info.ri_diskio_bytesread,
        physical_write_bytes=info.ri_diskio_byteswritten,
        reliable=True,
    )


def _linux_snapshot():
    path = Path("/proc/self/io")
    if not path.is_file():
        return None
    values = {
        key: int(value.strip())
        for key, value in (
            line.split(":", 1) for line in path.read_text().splitlines()
        )
    }
    return ProcessIoSnapshot(
        logical_write_bytes=values.get("wchar", 0),
        method="linux-proc-self-io",
        physical_read_bytes=values.get("read_bytes", 0),
        physical_write_bytes=values.get("write_bytes", 0),
        reliable="write_bytes" in values,
    )


def snapshot_process_io():
    """Return monotonic I/O counters for the current process."""
    snapshot = _darwin_snapshot() if sys.platform == "darwin" else _linux_snapshot()
    if snapshot is not None:
        return snapshot
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return ProcessIoSnapshot(
        logical_write_bytes=0,
        method="rusage-block-fallback",
        physical_read_bytes=max(0, usage.ru_inblock) * 512,
        physical_write_bytes=max(0, usage.ru_oublock) * 512,
        reliable=False,
    )
