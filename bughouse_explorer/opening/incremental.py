"""Durable, source-pinned incremental graph generations.

Internal keys never escape this store. Counts cover the complete replay, including
omitted tails. XOR of distinct game keys retains the sole owner after deletions
without storing every hidden placement posting; it is never a support estimate.
"""

from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import heapq
import struct
import itertools
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
import zlib

from bughouse_explorer.engine import Board
from .adapter import ADAPTER_POLICY_VERSION, OpeningGame
from .packed import _file_hash
from .position_graph import identity_key
from .position_graph_packed import UINT64, _metadata_payload
from .position_graph_streaming import (
    GRAPH_REPLAY_POLICY_VERSION,
    PositionReplayError,
    _replay_game,
    _outcome_code,
    _discover_position_keys,
    create_graph_schema,
    export_graph_facts,
)
from .publication import validate_artifact

VERSION = 1
SUPPORT_RECORDS_PER_CHUNK = 2_000_000
TERMINAL = "last-shared-placement-plus-one-or-game-end-v1"


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def policy_identity():
    from bughouse_explorer import engine, tcn
    from . import adapter, position_graph, position_graph_streaming

    return {
        "schema": VERSION,
        "adapter": ADAPTER_POLICY_VERSION,
        "replay": GRAPH_REPLAY_POLICY_VERSION,
        "terminal": TERMINAL,
        "implementation": {
            Path(m.__file__).name: _file_hash(Path(m.__file__))
            for m in (engine, tcn, adapter, position_graph, position_graph_streaming)
        },
    }


def load_game(payload):
    if payload is None:
        return None
    fields = json.loads(payload)
    fields["move_tokens"] = tuple(fields["move_tokens"])
    fields["provenance_flags"] = tuple(fields["provenance_flags"])
    return OpeningGame(**fields)


@dataclass(frozen=True)
class Revision:
    source_order: int
    uuid: str
    raw: str
    game: OpeningGame | None
    admission: str | None
    replay_fingerprint: str

    @classmethod
    def from_game(cls, order, game):
        raw = encoded(asdict(game))
        return cls(
            order,
            game.uuid,
            raw,
            game,
            None,
            hashlib.sha256(encoded(game.move_tokens).encode()).hexdigest(),
        )

    @classmethod
    def from_row(cls, row, adapter):
        raw = dict(row)
        outcome = adapter.outcome_from_row(row)
        replay = [raw[k] for k in ("tcn", "rules", "initial_setup")]
        return cls(
            raw["source_rowid"],
            raw["uuid"],
            encoded(raw),
            outcome.game,
            outcome.skip_reason,
            hashlib.sha256(encoded(replay).encode()).hexdigest(),
        )


class Generation:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.path = self.directory / "checkpoint.sqlite3"

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, uri=True)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=FULL")
        c.execute("PRAGMA cache_size=-262144")
        c.create_function("xor_keys", 2, lambda a, b: a ^ b)

        class OwnerXor:
            def __init__(self):
                self.value = 0

            def step(self, key):
                self.value ^= key

            def finalize(self):
                return self.value

        c.create_aggregate("owner_xor_aggregate", 1, OwnerXor)
        try:
            with c:
                yield c
        finally:
            c.close()

    @classmethod
    def create(cls, directory, *, source_fingerprint, parent=None):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        gen = cls(directory)
        if parent:
            parent.verify_complete()
            with sqlite3.connect(
                f"{parent.path.as_uri()}?mode=ro&immutable=1", uri=True
            ) as src:
                with sqlite3.connect(gen.path) as dst:
                    src.backup(dst)
        with gen.connect() as c:
            if not parent:
                create_graph_schema(c)
                c.executescript(
                    """
                CREATE TABLE ledger(
                  game_key INTEGER PRIMARY KEY, uuid TEXT UNIQUE NOT NULL,
                  source_order INTEGER NOT NULL, raw TEXT NOT NULL,
                  game TEXT, admission TEXT, replay_fingerprint TEXT NOT NULL,
                  outcome TEXT NOT NULL, error TEXT);
                CREATE TABLE support(
                  key BLOB PRIMARY KEY, count INTEGER NOT NULL CHECK(count>=0),
                  owner_xor INTEGER NOT NULL) WITHOUT ROWID;
                CREATE TABLE revisions(
                  generation TEXT, game_key INTEGER, raw TEXT, game TEXT,
                  outcome TEXT, PRIMARY KEY(generation,game_key)) WITHOUT ROWID;
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE INDEX position_games_game ON position_games(ordinal);
                CREATE INDEX state_games_game ON state_games(ordinal);
                CREATE INDEX edge_games_game ON edge_games(ordinal);
                CREATE INDEX endings_game ON endings(ordinal);
                CREATE INDEX posting_entries_game ON posting_entries(ordinal);
                """
                )
            # Only per-generation job tables are reset in the new child copy.
            for table in ("incoming", "changes", "touched", "repairs"):
                c.execute(f"DROP TABLE IF EXISTS {table}")
            c.executescript(
                """
            CREATE TABLE incoming(
              game_key INTEGER PRIMARY KEY, uuid TEXT UNIQUE NOT NULL,
              source_order INTEGER UNIQUE NOT NULL, raw TEXT NOT NULL,
              game TEXT, admission TEXT, replay_fingerprint TEXT NOT NULL,
              outcome TEXT NOT NULL, error TEXT);
            CREATE TABLE changes(game_key INTEGER PRIMARY KEY, topology INTEGER NOT NULL);
            CREATE TABLE touched(key BLOB PRIMARY KEY, old_count INTEGER NOT NULL,
              old_owner INTEGER NOT NULL) WITHOUT ROWID;
            CREATE TABLE repairs(game_key INTEGER PRIMARY KEY, reason TEXT NOT NULL,
              old_edges INTEGER, new_edges INTEGER, old_ending INTEGER, new_ending INTEGER);
            DELETE FROM meta;
            """
            )
            for key, value in {
                "source": source_fingerprint,
                "generation_identity": str(gen.directory),
                "policy": policy_identity(),
                "parent": str(parent.directory) if parent else None,
                "stage": "ingest",
                "ingest_cursor": -1,
                "support_cursor": -1,
                "repair_cursor": -1,
                "support_replayed_games": 0,
                "started": time.time(),
                "timings": {},
            }.items():
                gen.set(c, key, value)
        return gen

    @classmethod
    def open(cls, directory, *, source_fingerprint):
        gen = cls(directory)
        if not gen.path.is_file():
            raise FileNotFoundError(gen.path)
        with gen.connect() as c:
            if gen.get(c, "source") != source_fingerprint:
                raise ValueError("source fingerprint mismatch")
            if gen.get(c, "policy") != policy_identity():
                raise ValueError(
                    "checkpoint policy/engine mismatch; explicit rebuild required"
                )
        return gen

    @staticmethod
    def get(c, key):
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if not row:
            raise ValueError(f"incomplete checkpoint metadata: {key}")
        return json.loads(row[0])

    @staticmethod
    def set(c, key, value):
        c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, encoded(value)))

    @property
    def source_fingerprint(self):
        with self.connect() as c:
            return self.get(c, "source")

    def run(self, revisions, *, interrupt_after=None, progress=None):
        with (self.directory / "writer.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("generation already has an active writer") from error
            return self._run(
                revisions, interrupt_after=interrupt_after, progress=progress
            )

    def _run(self, revisions, *, interrupt_after=None, progress=None):
        if (self.directory / "complete.json").exists():
            self.verify_complete()
            return
        with self.connect() as c:
            if self.get(c, "policy") != policy_identity():
                raise ValueError("checkpoint policy/engine mismatch")
            for stage, next_stage in [
                ("ingest", "support"),
                ("support", "repair"),
                ("repair", "verify"),
                ("verify", "complete"),
            ]:
                if self.get(c, "stage") != stage:
                    continue
                started = time.monotonic()
                if progress:
                    progress({"stage": stage, "event": "start"})
                getattr(self, "_" + stage)(c, revisions, progress)
                timings = self.get(c, "timings")
                timings[stage] = timings.get(stage, 0) + time.monotonic() - started
                self.set(c, "timings", timings)
                self.set(c, "stage", next_stage)
                c.commit()
                if interrupt_after == stage:
                    raise InterruptedError(stage)
            if self.get(c, "stage") != "complete":
                raise ValueError("incomplete generation")
            checkpoint = c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint[0] != 0:
                raise ValueError(
                    "checkpoint is blocked by an active reader; release it and resume"
                )
        completion = self.directory / "complete.json"
        if not completion.exists():
            payload = {
                "sha256": _file_hash(self.path),
                "bytes": self.path.stat().st_size,
                "source": self.source_fingerprint,
                "policy": policy_identity(),
                "metrics": self.metrics(),
            }
            temp = self.directory / "complete.pending.json"
            with temp.open("w") as f:
                f.write(encoded(payload) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, completion)
        if interrupt_after == "complete":
            raise InterruptedError("complete")
        self.verify_complete()

    def configure_seed(self, certificate):
        with (self.directory / "writer.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("generation already has an active writer") from error
            return self._configure_seed(certificate)

    def _configure_seed(self, certificate):
        """Bind a byte-validated seed only before bootstrap support discovery."""
        certificate = Path(certificate).resolve()
        record = json.loads(certificate.read_text())
        if _file_hash(Path(record["staging"])) != record["staging_sha256"]:
            raise ValueError("seed staging checksum mismatch")
        if (
            _file_hash(Path(record["artifact"]) / "manifest.json")
            != record["manifest_sha256"]
        ):
            raise ValueError("seed artifact manifest mismatch")
        validate_artifact(record["artifact"])
        with self.connect() as c:
            if self.get(c, "parent") is not None or self.get(c, "stage") != "ingest":
                raise ValueError("seed can only be bound during bootstrap ingestion")
            if self.get(c, "source") != record["source_fingerprint"]:
                raise ValueError("seed source mismatch")
            existing = c.execute("SELECT value FROM meta WHERE key='seed'").fetchone()
            if existing and json.loads(existing[0]) != record:
                raise ValueError("seed identity cannot change on resume")
            self.set(c, "seed", record)
            c.execute(
                "CREATE TABLE IF NOT EXISTS seed_games(ordinal INTEGER PRIMARY KEY,uuid TEXT UNIQUE,metadata_hash TEXT)"
            )
            cursor = c.execute(
                "SELECT COALESCE(MAX(ordinal),-1) FROM seed_games"
            ).fetchone()[0]
            from .position_graph_packed import PackedPositionGraph

            with PackedPositionGraph(record["artifact"]) as reader:
                for ordinal in range(cursor + 1, record["games"]):
                    game = reader.game(ordinal)
                    digest = hashlib.sha256(encoded(game).encode()).hexdigest()
                    c.execute(
                        "INSERT INTO seed_games VALUES (?,?,?)",
                        (ordinal, game["uuid"], digest),
                    )
                    if ordinal % 10000 == 0:
                        c.commit()
            c.commit()

    def _ingest(self, c, revisions, progress):
        cursor = self.get(c, "ingest_cursor")
        next_key = c.execute(
            "SELECT COALESCE(MAX(game_key),0)+1 FROM ledger"
        ).fetchone()[0]
        next_key = max(
            next_key,
            c.execute("SELECT COALESCE(MAX(game_key),0)+1 FROM incoming").fetchone()[0],
        )
        seed = c.execute("SELECT value FROM meta WHERE key='seed'").fetchone()
        seen_order = -1
        for revision in revisions:
            if revision.source_order <= seen_order:
                raise ValueError("source order must be strictly increasing")
            seen_order = revision.source_order
            if revision.source_order <= cursor:
                continue
            old = c.execute(
                "SELECT game_key,replay_fingerprint,admission,outcome,error FROM ledger WHERE uuid=?",
                (revision.uuid,),
            ).fetchone()
            key = old[0] if old else next_key
            if not old:
                next_key += 1
            outcome, error = revision.admission or "accepted", None
            if revision.game is not None:
                if (
                    old
                    and old[1] == revision.replay_fingerprint
                    and old[2] is None
                    and old[3] != "deleted"
                ):
                    outcome, error = old[3:5]
                elif seed and (
                    known := c.execute(
                        "SELECT metadata_hash FROM seed_games WHERE uuid=?",
                        (revision.uuid,),
                    ).fetchone()
                ):
                    actual = hashlib.sha256(
                        encoded(_metadata_payload(revision.game)).encode()
                    ).hexdigest()
                    if known[0] != actual:
                        raise ValueError("seed source-game metadata mismatch")
                else:
                    try:
                        _replay_game(revision.game)
                        if seed:
                            raise ValueError(
                                "replayable source game is absent from checked seed"
                            )
                    except PositionReplayError as exc:
                        outcome, error = "position_replay_error", str(exc)
            c.execute(
                "INSERT INTO incoming VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    key,
                    revision.uuid,
                    revision.source_order,
                    revision.raw,
                    encoded(asdict(revision.game)) if revision.game else None,
                    revision.admission,
                    revision.replay_fingerprint,
                    outcome,
                    error,
                ),
            )
            self.set(c, "ingest_cursor", revision.source_order)
            if key % 1000 == 0:
                c.commit()
                if progress and key % 10000 == 0:
                    progress({"stage": "ingest", "source_order": revision.source_order})
        c.execute(
            """INSERT OR IGNORE INTO changes
          SELECT COALESCE(n.game_key,o.game_key),
                 CASE WHEN o.outcome='accepted' OR n.outcome='accepted' THEN
                   o.game_key IS NULL OR n.game_key IS NULL OR
                   o.replay_fingerprint IS NOT n.replay_fingerprint OR o.outcome IS NOT n.outcome
                 ELSE 0 END
          FROM ledger o LEFT JOIN incoming n ON n.game_key=o.game_key
          WHERE (n.game_key IS NULL AND o.outcome!='deleted') OR
                (n.game_key IS NOT NULL AND (n.raw IS NOT o.raw OR n.source_order IS NOT o.source_order OR o.outcome='deleted'))
          UNION ALL SELECT n.game_key, n.outcome='accepted' FROM incoming n
          LEFT JOIN ledger o ON n.game_key=o.game_key WHERE o.game_key IS NULL"""
        )
        revision_identity = encoded(
            {
                "source": self.get(c, "source"),
                "generation": self.get(c, "generation_identity"),
            }
        )
        c.execute(
            """INSERT OR IGNORE INTO revisions SELECT ?,l.game_key,l.raw,l.game,l.outcome
          FROM ledger l JOIN changes d ON d.game_key=l.game_key""",
            (revision_identity,),
        )
        c.commit()

    def _support(self, c, _revisions, progress):
        if self.get(c, "parent") is None:
            return self._bootstrap_support(c, progress)
        cursor = self.get(c, "support_cursor")
        replayed = self.get(c, "support_replayed_games")
        for (key,) in c.execute(
            "SELECT game_key FROM changes WHERE topology=1 AND game_key>? ORDER BY game_key",
            (cursor,),
        ):
            for table, sign in [("ledger", -1), ("incoming", 1)]:
                row = c.execute(
                    f"SELECT game,outcome FROM {table} WHERE game_key=?", (key,)
                ).fetchone()
                if not row or row[1] != "accepted":
                    continue
                game = load_game(row[0])
                root, _, transitions, _ = _replay_game(game)
                keys = {identity_key("position", root)} | {t[0] for t in transitions}
                for position in keys:
                    c.execute(
                        """INSERT OR IGNORE INTO touched SELECT key,count,owner_xor
                                 FROM support WHERE key=?""",
                        (position,),
                    )
                    c.execute(
                        "INSERT OR IGNORE INTO touched VALUES (?,0,0)", (position,)
                    )
                    if sign < 0:
                        updated = c.execute(
                            "UPDATE support SET count=count-1, owner_xor=xor_keys(owner_xor,?) WHERE key=? AND count>0",
                            (key, position),
                        )
                        if updated.rowcount != 1:
                            raise ValueError("missing previous placement revision")
                    else:
                        c.execute(
                            "INSERT INTO support VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1, owner_xor=xor_keys(owner_xor,excluded.owner_xor)",
                            (position, key),
                        )
                replayed += 1
            self.set(c, "support_cursor", key)
            self.set(c, "support_replayed_games", replayed)
            if key % 1000 == 0:
                c.commit()
            if progress and key % 10000 == 0:
                progress({"stage": "support", "game_key": key, "replayed": replayed})
        # Queue final-batch promotions/demotions, including hidden singleton owners.
        c.execute(
            """INSERT OR IGNORE INTO repairs(game_key,reason)
          SELECT DISTINCT t.old_owner,'promotion' FROM touched t JOIN support s ON s.key=t.key
          JOIN incoming n ON n.game_key=t.old_owner AND n.outcome='accepted'
          WHERE t.old_count=1 AND s.count>=2"""
        )
        c.execute(
            """INSERT OR IGNORE INTO repairs(game_key,reason)
          SELECT DISTINCT s.owner_xor,'demotion' FROM touched t JOIN support s ON s.key=t.key
          JOIN incoming n ON n.game_key=s.owner_xor AND n.outcome='accepted'
          WHERE t.old_count>=2 AND s.count=1"""
        )
        c.execute(
            """INSERT OR IGNORE INTO repairs(game_key,reason)
          SELECT game_key,'source_change' FROM changes"""
        )
        c.execute("DELETE FROM support WHERE count=0 AND owner_xor=0")
        c.commit()

    def _bootstrap_support(self, c, progress):
        """Durable external sort; retained spills are discovery facts, not replay cache."""
        record = struct.Struct(">20sQ")
        c.execute(
            "CREATE TABLE IF NOT EXISTS support_chunks(number INTEGER PRIMARY KEY,path TEXT,sha256 TEXT,last_game INTEGER)"
        )
        cursor = self.get(c, "support_cursor")
        replayed = self.get(c, "support_replayed_games")
        number = c.execute(
            "SELECT COALESCE(MAX(number),-1)+1 FROM support_chunks"
        ).fetchone()[0]
        buffer = []
        last = cursor

        def flush():
            nonlocal number, buffer
            if not buffer:
                return
            buffer.sort()
            # A crash can leave an unregistered spill; retain it and choose a fresh name.
            import uuid

            path = self.directory / f"support-{number:06d}-{uuid.uuid4().hex}.bin"
            with path.open("xb") as stream:
                stream.writelines(buffer)
                stream.flush()
                os.fsync(stream.fileno())
            c.execute(
                "INSERT INTO support_chunks VALUES (?,?,?,?)",
                (number, str(path), _file_hash(path), last),
            )
            self.set(c, "support_cursor", last)
            self.set(c, "support_replayed_games", replayed)
            c.commit()
            if progress:
                progress(
                    {
                        "stage": "support_discovery",
                        "games": replayed,
                        "chunk": number,
                        "bytes": path.stat().st_size,
                    }
                )
            number += 1
            buffer = []

        for key, payload in c.execute(
            "SELECT game_key,game FROM incoming WHERE outcome='accepted' AND game_key>? ORDER BY game_key",
            (cursor,),
        ):
            keys = _discover_position_keys(load_game(payload))
            buffer.extend(record.pack(position, key) for position in keys)
            replayed += 1
            last = key
            if len(buffer) >= SUPPORT_RECORDS_PER_CHUNK:
                flush()
        flush()
        paths = []
        for path, digest in c.execute(
            "SELECT path,sha256 FROM support_chunks ORDER BY number"
        ):
            path = Path(path)
            if _file_hash(path) != digest:
                raise ValueError("discovery spill checksum mismatch")
            paths.append(path)

        def records(path):
            with path.open("rb") as stream:
                while block := stream.read(record.size * 32768):
                    if len(block) % record.size:
                        raise ValueError("partial support record")
                    yield from record.iter_unpack(block)

        marker = c.execute(
            "SELECT value FROM meta WHERE key='support_merge_cursor'"
        ).fetchone()
        marker = bytes.fromhex(json.loads(marker[0])) if marker else b""
        batch = []
        for position, group in itertools.groupby(
            heapq.merge(*(records(path) for path in paths)), key=lambda row: row[0]
        ):
            if position <= marker:
                continue
            count = 0
            owner = 0
            previous = None
            for _, key in group:
                if key == previous:
                    raise ValueError("duplicate complete placement contribution")
                count += 1
                owner ^= key
                previous = key
            batch.append((position, count, owner))
            if len(batch) >= 20000:
                c.executemany("INSERT INTO support VALUES (?,?,?)", batch)
                self.set(c, "support_merge_cursor", position.hex())
                c.commit()
                batch = []
        if batch:
            c.executemany("INSERT INTO support VALUES (?,?,?)", batch)
            self.set(c, "support_merge_cursor", batch[-1][0].hex())
            c.commit()
        c.execute(
            "INSERT OR IGNORE INTO repairs(game_key,reason) SELECT game_key,'source_change' FROM changes"
        )
        c.commit()

    def _repair(self, c, _revisions, progress):
        seed = c.execute("SELECT value FROM meta WHERE key='seed'").fetchone()
        if seed:
            return self._seed_materialized(c, json.loads(seed[0]), progress)
        cursor = self.get(c, "repair_cursor")
        for key, reason in c.execute(
            "SELECT game_key,reason FROM repairs WHERE game_key>? ORDER BY game_key",
            (cursor,),
        ):
            old_edges = c.execute(
                "SELECT count(*) FROM edge_games WHERE ordinal=?", (key,)
            ).fetchone()[0]
            old_ending = c.execute(
                "SELECT count(*) FROM endings WHERE ordinal=?", (key,)
            ).fetchone()[0]
            new = c.execute(
                "SELECT game,outcome FROM incoming WHERE game_key=?", (key,)
            ).fetchone()
            changed = c.execute(
                "SELECT topology FROM changes WHERE game_key=?", (key,)
            ).fetchone()
            old = c.execute(
                "SELECT outcome FROM ledger WHERE game_key=?", (key,)
            ).fetchone()
            topology = reason != "source_change" or (changed and changed[0])
            # Metadata-only changes replace outcomes and postings without topology replay.
            if not topology and new and old and new[1] == old[0] == "accepted":
                game = load_game(new[0])
                outcome = _outcome_code(game)
                c.execute(
                    "UPDATE state_games SET outcome=? WHERE ordinal=?", (outcome, key)
                )
                c.execute(
                    "UPDATE edge_games SET outcome=? WHERE ordinal=?", (outcome, key)
                )
                c.execute("DELETE FROM posting_entries WHERE ordinal=?", (key,))
                self._postings(c, key, game)
            else:
                for table in (
                    "position_games",
                    "state_games",
                    "edge_games",
                    "endings",
                    "posting_entries",
                ):
                    c.execute(f"DELETE FROM {table} WHERE ordinal=?", (key,))
                if new and new[1] == "accepted":
                    self._materialize(c, key, load_game(new[0]))
            c.execute(
                "UPDATE repairs SET old_edges=?,new_edges=(SELECT count(*) FROM edge_games WHERE ordinal=?), old_ending=?,new_ending=(SELECT count(*) FROM endings WHERE ordinal=?) WHERE game_key=?",
                (old_edges, key, old_ending, key, key),
            )
            self.set(c, "repair_cursor", key)
            if key % 1000 == 0:
                c.commit()
            if progress and key % 10000 == 0:
                progress({"stage": "repair", "game_key": key})
        c.execute(
            "UPDATE ledger SET outcome='deleted',admission='deleted',game=NULL "
            "WHERE game_key IN (SELECT game_key FROM changes) "
            "AND game_key NOT IN (SELECT game_key FROM incoming)"
        )
        # Promotion-only repairs change graph facts, not source revisions. Drive
        # revision writes from the changed-key set, avoiding a full ledger rewrite.
        c.execute(
            "INSERT OR REPLACE INTO ledger "
            "SELECT n.* FROM changes d CROSS JOIN incoming n "
            "WHERE n.game_key=d.game_key"
        )
        c.commit()

    def _seed_materialized(self, c, seed, progress):
        if _file_hash(Path(seed["staging"])) != seed["staging_sha256"]:
            raise ValueError("seed staging changed")
        count = c.execute(
            "SELECT count(*) FROM incoming WHERE outcome='accepted'"
        ).fetchone()[0]
        if count != seed["games"]:
            raise ValueError("seed accepted count differs from source")
        # Validate ALL source metadata, including rows ingested before a resumed seed binding.
        for payload, expected in c.execute(
            """SELECT i.game,s.metadata_hash FROM incoming i
          LEFT JOIN seed_games s ON s.uuid=i.uuid WHERE i.outcome='accepted'"""
        ):
            if (
                expected
                != hashlib.sha256(
                    encoded(_metadata_payload(load_game(payload))).encode()
                ).hexdigest()
            ):
                raise ValueError("seed source-game metadata mismatch")
        c.execute(
            "ATTACH DATABASE ? AS seed",
            (Path(seed["staging"]).as_uri() + "?mode=ro&immutable=1",),
        )
        c.execute("CREATE TABLE IF NOT EXISTS seeded_tables(name TEXT PRIMARY KEY)")
        for table in (
            "positions",
            "states",
            "edges",
            "position_games",
            "state_games",
            "edge_games",
            "endings",
            "posting_entries",
        ):
            if c.execute(
                "SELECT 1 FROM seeded_tables WHERE name=?", (table,)
            ).fetchone():
                continue
            if table in ("positions", "states", "edges"):
                c.execute(f"INSERT INTO {table} SELECT * FROM seed.{table}")
            else:
                column = {
                    "position_games": "position_key",
                    "state_games": "state_key",
                    "edge_games": "edge_key",
                    "endings": "state_key",
                    "posting_entries": "posting_key",
                }[table]
                outcome = ",f.outcome" if table in ("state_games", "edge_games") else ""
                c.execute(
                    f"""INSERT INTO {table} SELECT f.{column},i.game_key{outcome}
                  FROM seed.{table} f JOIN seed_games s ON s.ordinal=f.ordinal
                  JOIN incoming i ON i.uuid=s.uuid"""
                )
            c.execute("INSERT INTO seeded_tables VALUES (?)", (table,))
            c.commit()
            if progress:
                progress({"stage": "seed_materialized", "table": table})
        c.execute("DELETE FROM ledger")
        c.execute("INSERT INTO ledger SELECT * FROM incoming")
        c.commit()

    @staticmethod
    def _postings(c, key, game):
        c.executemany(
            "INSERT INTO posting_entries VALUES (?,?)",
            [
                (f"white\0{game.white_username.casefold()}", key),
                (f"black\0{game.black_username.casefold()}", key),
            ],
        )

    def _materialize(self, c, key, game):
        root, fen, transitions, final = _replay_game(game)
        root_key = identity_key("position", root)
        state_key = identity_key("state", fen)
        last = 0
        for index, t in enumerate(transitions, 1):
            support = c.execute(
                "SELECT count FROM support WHERE key=?", (t[0],)
            ).fetchone()
            if support is None or support[0] < 1:
                raise ValueError("complete support is missing a replayed placement")
            if support[0] >= 2:
                last = index
        limit = min(len(transitions), last + 1)
        c.execute("INSERT OR IGNORE INTO positions VALUES (?,?)", (root_key, root))
        c.execute(
            "INSERT OR IGNORE INTO states VALUES (?,?,?)", (state_key, root_key, fen)
        )
        positions = {root_key}
        states = {state_key}
        edges = set()
        for pk, placement, sk, state, ek, parent, move, label in transitions[:limit]:
            c.execute("INSERT OR IGNORE INTO positions VALUES (?,?)", (pk, placement))
            c.execute("INSERT OR IGNORE INTO states VALUES (?,?,?)", (sk, pk, state))
            c.execute(
                "INSERT OR IGNORE INTO edges VALUES (?,?,?,?,?)",
                (ek, parent, move, sk, label),
            )
            positions.add(pk)
            states.add(sk)
            edges.add(ek)
        outcome = _outcome_code(game)
        c.executemany(
            "INSERT INTO position_games VALUES (?,?)", ((p, key) for p in positions)
        )
        c.executemany(
            "INSERT INTO state_games VALUES (?,?,?)",
            ((s, key, outcome) for s in states),
        )
        c.executemany(
            "INSERT INTO edge_games VALUES (?,?,?)", ((e, key, outcome) for e in edges)
        )
        if limit == len(transitions):
            c.execute(
                "INSERT INTO endings VALUES (?,?)", (identity_key("state", final), key)
            )
        self._postings(c, key, game)

    def _verify(self, c, _revisions, progress):
        if c.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("checkpoint integrity failure")
        if c.execute("SELECT 1 FROM support WHERE count<=0 LIMIT 1").fetchone():
            raise ValueError("zero or negative placement support")
        if c.execute(
            """SELECT 1 FROM support s LEFT JOIN ledger l ON l.game_key=s.owner_xor
                        WHERE s.count=1 AND (l.game_key IS NULL OR l.outcome!='accepted') LIMIT 1"""
        ).fetchone():
            raise ValueError("singleton owner is not an accepted game")
        if c.execute(
            """SELECT 1 FROM support s WHERE s.count>=2 AND s.count !=
          (SELECT count(*) FROM position_games f WHERE f.position_key=s.key) LIMIT 1"""
        ).fetchone():
            raise ValueError(
                "shared placement support differs from complete materialized membership"
            )
        if c.execute(
            """SELECT 1 FROM support s WHERE s.count>=2 AND s.owner_xor IS NOT
          (SELECT owner_xor_aggregate(f.ordinal) FROM position_games f WHERE f.position_key=s.key) LIMIT 1"""
        ).fetchone():
            raise ValueError("shared placement owner accumulator mismatch")
        # Untouched hidden owners are protected by the parent's complete checksum.
        # Independently replay every final singleton owner touched by this batch.
        current_owner = None
        keys = set()
        for owner, position in c.execute(
            """SELECT s.owner_xor,s.key FROM touched t
          JOIN support s ON s.key=t.key WHERE s.count=1 ORDER BY s.owner_xor,s.key"""
        ):
            if owner != current_owner:
                payload = c.execute(
                    "SELECT game FROM ledger WHERE game_key=? AND outcome='accepted'",
                    (owner,),
                ).fetchone()
                if payload is None:
                    raise ValueError("missing singleton owner revision")
                keys = _discover_position_keys(load_game(payload[0]))
                current_owner = owner
            if position not in keys:
                raise ValueError("singleton owner does not visit its placement")
        root = identity_key("position", Board().placement())
        accepted = c.execute(
            "SELECT count(*) FROM ledger WHERE outcome='accepted'"
        ).fetchone()[0]
        if not accepted:
            raise ValueError(
                "packed graph artifacts require at least one accepted game"
            )
        row = c.execute("SELECT count FROM support WHERE key=?", (root,)).fetchone()
        if row != (accepted,):
            raise ValueError("complete root support does not reconcile")
        if (
            c.execute(
                "SELECT count(*) FROM position_games WHERE position_key=?", (root,)
            ).fetchone()[0]
            != accepted
        ):
            raise ValueError("materialized root support does not reconcile")
        for table in (
            "position_games",
            "state_games",
            "edge_games",
            "endings",
            "posting_entries",
        ):
            if c.execute(
                f"""SELECT 1 FROM {table} f LEFT JOIN ledger l ON l.game_key=f.ordinal
                             WHERE l.game_key IS NULL OR l.outcome!='accepted' LIMIT 1"""
            ).fetchone():
                raise ValueError("membership references an excluded/missing game")
        if (
            c.execute("SELECT count(*) FROM posting_entries").fetchone()[0]
            != 2 * accepted
        ):
            raise ValueError("player posting count mismatch")

    def verify_complete(self):
        completion = self.directory / "complete.json"
        if not completion.is_file():
            raise ValueError("incomplete parent generation")
        record = json.loads(completion.read_text())
        wal = Path(str(self.path) + "-wal")
        if wal.exists() and wal.stat().st_size:
            raise ValueError("completed generation has an uncheckpointed WAL")
        if record["policy"] != policy_identity():
            raise ValueError("checkpoint policy/engine mismatch")
        if (
            self.path.stat().st_size != record["bytes"]
            or _file_hash(self.path) != record["sha256"]
        ):
            raise ValueError("checkpoint checksum mismatch")
        with closing(
            sqlite3.connect(f"{self.path.as_uri()}?mode=ro&immutable=1", uri=True)
        ) as c:
            if (
                self.get(c, "stage") != "complete"
                or self.get(c, "source") != record["source"]
            ):
                raise ValueError(
                    "completion manifest does not match checkpoint metadata"
                )
            if self.get(c, "policy") != record["policy"]:
                raise ValueError("checkpoint policy/engine mismatch")
        return record

    def metrics(self):
        with self.connect() as c:
            counts = dict(
                c.execute("SELECT outcome,count(*) FROM ledger GROUP BY outcome")
            )
            deleted = counts.pop("deleted", 0)
            return {
                "deleted": deleted,
                "accepted": counts.pop("accepted", 0),
                "skipped": counts,
                "stage": self.get(c, "stage"),
                "timings": self.get(c, "timings"),
                "elapsed_wall_seconds_including_interruptions": time.time()
                - self.get(c, "started"),
                "support_replayed_games": self.get(c, "support_replayed_games"),
                "placements": c.execute("SELECT count(*) FROM support").fetchone()[0],
                "shared": c.execute(
                    "SELECT count(*) FROM support WHERE count>=2"
                ).fetchone()[0],
                "repairs": dict(
                    c.execute("SELECT reason,count(*) FROM repairs GROUP BY reason")
                ),
            }

    def export(self, directory):
        self.verify_complete()
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        scratch = directory.parent / (directory.name + "-export.sqlite3")
        if scratch.exists():
            raise FileExistsError(scratch)
        c = sqlite3.connect(scratch, uri=True)
        c.execute("PRAGMA temp_store=FILE")
        c.execute("PRAGMA cache_size=-262144")
        c.execute(
            "ATTACH DATABASE ? AS checkpoint",
            (f"{self.path.as_uri()}?mode=ro&immutable=1",),
        )
        c.execute(
            "CREATE TABLE export_games(game_key INTEGER PRIMARY KEY, ordinal INTEGER UNIQUE)"
        )
        c.executemany(
            "INSERT INTO export_games VALUES (?,?)",
            (
                (key, i)
                for i, (key,) in enumerate(
                    c.execute(
                        "SELECT game_key FROM checkpoint.ledger WHERE outcome='accepted' ORDER BY source_order"
                    )
                )
            ),
        )
        for table, column in [
            ("position_games", "position_key"),
            ("state_games", "state_key"),
            ("edge_games", "edge_key"),
            ("endings", "state_key"),
            ("posting_entries", "posting_key"),
        ]:
            outcome = ",f.outcome" if table in ("state_games", "edge_games") else ""
            c.execute(
                f"""CREATE TEMP VIEW {table} AS SELECT f.{column},g.ordinal{outcome}
                          FROM checkpoint.{table} f JOIN export_games g ON g.game_key=f.ordinal"""
            )
        for table, facts, key in [
            ("positions", "position_games", "position_key"),
            ("states", "state_games", "state_key"),
            ("edges", "edge_games", "edge_key"),
        ]:
            c.execute(
                f"""CREATE TEMP VIEW {table} AS SELECT s.* FROM checkpoint.{table} s
                          WHERE EXISTS(SELECT 1 FROM checkpoint.{facts} f WHERE f.{key}=s.key)"""
            )
        digest = hashlib.blake2b(digest_size=20)
        digest.update(b"opening-position-graph-v1\0")
        digest.update(self.source_fingerprint.encode())
        with (
            (directory / "games.bin").open("wb") as games,
            (directory / "game_offsets.bin").open("wb") as offsets,
        ):
            for (payload,) in c.execute(
                """SELECT l.game FROM checkpoint.ledger l
              JOIN export_games g ON g.game_key=l.game_key ORDER BY g.ordinal"""
            ):
                game = load_game(payload)
                for value in (game.uuid, "".join(game.move_tokens), game.content_hash):
                    digest.update(b"\0")
                    digest.update(value.encode())
                offsets.write(UINT64.pack(games.tell()))
                games.write(
                    zlib.compress(encoded(_metadata_payload(game)).encode(), level=6)
                )
            offsets.write(UINT64.pack(games.tell()))
        metrics = self.metrics()
        try:
            report = export_graph_facts(
                c,
                directory,
                staging_path=scratch,
                accepted=metrics["accepted"],
                observed_skipped=metrics["skipped"],
                observed_input_digest=digest.hexdigest(),
                source_fingerprint=self.source_fingerprint,
                terminal_policy=TERMINAL,
                shared_positions_count=metrics["shared"],
            )
        finally:
            c.close()
        validate_artifact(directory)
        return report


def validate_materialized_seed(staging, artifact, output):
    """Prove retained staging against every reference component without mutating it."""
    staging = Path(staging).resolve()
    artifact = Path(artifact).resolve()
    output = Path(output)
    validate_artifact(artifact)
    manifest = json.loads((artifact / "manifest.json").read_text())
    if (
        manifest["format_version"] != "packed-position-graph-v1"
        or manifest["terminal_policy"] != TERMINAL
    ):
        raise ValueError("seed must use the current semantic graph contract")
    output.mkdir(parents=True, exist_ok=False)
    scratch = output / "validation.sqlite3"
    with sqlite3.connect(scratch, uri=True) as c:
        c.execute(
            "ATTACH DATABASE ? AS seed", (f"{staging.as_uri()}?mode=ro&immutable=1",)
        )
        if c.execute("PRAGMA seed.quick_check").fetchall() != [("ok",)]:
            raise ValueError("retained staging integrity failure")
        for table in (
            "positions",
            "states",
            "edges",
            "position_games",
            "state_games",
            "edge_games",
            "endings",
            "posting_entries",
        ):
            c.execute(f"CREATE TEMP VIEW {table} AS SELECT * FROM seed.{table}")
        exported = output / "artifact"
        exported.mkdir()
        for name in ("games.bin", "game_offsets.bin"):
            shutil.copyfile(artifact / name, exported / name)
        export_graph_facts(
            c,
            exported,
            staging_path=scratch,
            accepted=manifest["games"],
            observed_skipped={},
            observed_input_digest=manifest["build_id"],
            source_fingerprint=manifest["source_fingerprint"],
            terminal_policy=TERMINAL,
            shared_positions_count=manifest["shared_positions"],
        )
    rebuilt = json.loads((exported / "manifest.json").read_text())
    if rebuilt != manifest:
        raise ValueError("retained staging differs from the exact reference artifact")
    record = {
        "staging": str(staging),
        "staging_sha256": _file_hash(staging),
        "artifact": str(artifact),
        "manifest_sha256": _file_hash(artifact / "manifest.json"),
        "source_fingerprint": manifest["source_fingerprint"],
        "games": manifest["games"],
    }
    (output / "validated-seed.json").write_text(encoded(record) + "\n")
    return record
