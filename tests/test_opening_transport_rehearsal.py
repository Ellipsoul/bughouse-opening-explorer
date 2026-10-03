"""The release rehearsal must remain local and recover its exact received bytes."""

import json
from dataclasses import replace
from pathlib import Path
import runpy

from bughouse_explorer.opening.position_graph_packed import build_packed_position_graph
from bughouse_explorer.opening.position_graph_v2 import repack_position_graph_v2
from opening_fixtures import corpus


def test_local_receiver_interruption_retry_and_reconstruction(tmp_path):
    semantic = tmp_path / "semantic"
    games = [
        replace(
            game,
            uuid=f"00000000-0000-4000-8000-{i:012x}",
            url=f"https://www.chess.com/game/live/{1000+i}",
        )
        for i, game in enumerate(corpus(), 1)
    ]
    build_packed_position_graph(
        games, semantic, source_fingerprint="local-rehearsal-fixture"
    )
    serving = tmp_path / "representative-mod71-v2-a"
    repack_position_graph_v2(semantic, serving)
    rehearse = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts/rehearse_opening_transport_locally.py")
    )["rehearse"]
    result = rehearse(serving, tmp_path / "rehearsal")
    assert result["external_writes"] is False
    assert result["exact_reconstruction"]
    assert result["resume"]["retries"] == 1
    assert result["resume"]["chunks_reused"] == 1
    assert result["completed_retry"]["chunks_uploaded"] == 0
    assert result["completed_retry"]["bytes_reused"] == result["source_bytes"]
    assert result["retained_partial_bytes"] > 0
    restored = tmp_path / "rehearsal/reconstructed" / serving.name
    assert {p.name: p.read_bytes() for p in serving.iterdir()} == {
        p.name: p.read_bytes() for p in restored.iterdir()
    }
    stage = json.loads((tmp_path / "rehearsal/stage/bundle-manifest.json").read_text())
    assert not any(p["path"].endswith((".db", ".sqlite3")) for p in stage["files"])
