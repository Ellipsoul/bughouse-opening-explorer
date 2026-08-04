import os
import sys

from bughouse_explorer.opening.process_io import snapshot_process_io


def test_process_io_snapshot_reports_fsynced_writes_on_supported_hosts(tmp_path):
    before = snapshot_process_io()
    payload = b"x" * (1024 * 1024)
    target = tmp_path / "write-probe.bin"

    with target.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())

    after = snapshot_process_io()

    assert after.physical_write_bytes >= before.physical_write_bytes
    assert after.logical_write_bytes >= before.logical_write_bytes
    assert after.method
    if sys.platform == "darwin":
        assert before.reliable and after.reliable
        assert after.physical_write_bytes - before.physical_write_bytes >= len(payload)
        assert after.logical_write_bytes - before.logical_write_bytes >= len(payload)
