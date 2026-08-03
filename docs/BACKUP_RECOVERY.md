# Raw database backup and recovery

This runbook protects `data/crawler.db`, the lossless source of truth for the
Bughouse corpus. Backup compression is an archival transport concern only. It
must not change the live database schema, payload encoding, parser behavior, or
query path.

## Recovery contract

A usable recovery point must satisfy all of these conditions:

1. It is a transactionally consistent SQLite snapshot, not an unchecked file
   copy made while WAL state may be changing.
2. Its compressed representation passes an integrity test and has a recorded
   SHA-256 checksum.
3. It has been decompressed to a different path and opened successfully.
4. The restored database passes `PRAGMA quick_check` and a complete
   `PRAGMA foreign_key_check`.
5. Core row counts and qualification/closure invariants match the source
   snapshot.
6. A verified copy exists outside the live database project path. Under the
   current accepted threat model it may be on the same host; host and volume
   failure are explicitly out of scope until the operator broadens the policy.
7. The restore command, verification evidence, artifact size, checksum,
   creation time, and storage location are documented.

Until every condition holds for the accepted threat model, the artifact is a
useful copy but not a complete recovery system.

## Current recovery state

The live database is:

```text
data/crawler.db
```

The checked post-qualification-reconciliation compressed artifact created on
2 August 2026 is:

```text
/Users/aronteh/Desktop/Coding_Adventures/bughouse/crawler-post-qualification-20260802.db.zst
```

It is 3,160,490,691 bytes and has SHA-256:

```text
90bc1778829eaf52bab881e0b02947e1635320a691f889330716635d94094872
```

Its checksum and restore-instruction sidecar is
`/Users/aronteh/Desktop/Coding_Adventures/bughouse/crawler-post-qualification-20260802.manifest.txt`.

Its 15,146,962,944-byte online-backup source and separately decompressed restore
are byte-identical and have SHA-256:

```text
04b5694a288f1b0a966524090e991d70aa695096531933710a0a17f25bb5a5ac
```

The first temporary restore drill at
`data/recovery/restore-drill-20260802/restored-crawler-post-qualification-20260802.db`
passed `PRAGMA quick_check`, the complete foreign-key scan, schema/count
comparison, qualification and fixed-window checks, active-work checks, and the
closure audit. That temporary file was later removed. Exact evidence and
commands are in the handoff. Reusable validation SQL is in
`scripts/validate_crawler_recovery.sql`.

The user-designated staging directory for this and future compressed backups is:

```text
/Users/aronteh/Desktop/Coding_Adventures/bughouse
```

The artifact and manifest were copied there and verified. The copied artifact
has the expected 3,160,490,691-byte size and compressed SHA-256, and it passed
`zstd --test`. A restore made specifically from that copied file was written to
`data/recovery/readback-drill-bughouse-dir-20260802/`, matched the checked
snapshot byte for byte, and passed the complete validation suite. That
temporary restore was later removed.

It and the repository are both on `/dev/disk3s5` on the same Mac. The operator
explicitly accepts that boundary for now: recovery protects against accidental
deletion or unintended irreversible live-database mutation, while host and
volume failure are out of scope. The designated copy and demonstrated read-back
therefore satisfy the current recovery contract and unblock product work.

The superseded pre-reconciliation artifact was:

```text
data/crawler-final-20260801.db.zst
```

Its recorded SHA-256 is:

```text
e0fcad6e6a8b91f3cf8fb288e0abb6215b38b0adb57c9d2670f6d16245cd2d12
```

That older artifact passed decompression-stream, SQLite integrity, foreign-key,
and core-count checks when it was created, but it predated the later 86-row
qualification reconciliation. The user authorized its deletion after the newer
designated backup and restore drill were verified.

All temporary uncompressed snapshots, restored drill databases, repository-local
compressed copies, and the duplicate local manifest were also deleted. Six
exact files totalling 51,761,869,319 bytes were removed; `data/` now contains
only the live `crawler.db`.

## Compression boundary

Whole-file Zstandard compression is appropriate for a cold backup because the
database is decompressed before SQLite opens it. It does not alter or obscure
anything in `crawler.db`; after decompression the restored bytes must exactly
match the uncompressed snapshot.

This is different from compressing `raw_payload` rows, changing UUID or hash
storage, using a compressed SQLite VFS, or removing normalized columns. Those
are live-storage design changes. They are deferred experiments and require
separate cloned-data benchmarks, round-trip proofs, parser/query measurements,
and explicit approval before any migration.

## Safe backup procedure

### 1. Preflight

Before writing a backup:

- confirm no crawler worker or durable run is active;
- confirm queued, leased, deferred, and failed job counts are zero;
- confirm closure is ready;
- inspect free space on both the backup and restore volumes;
- record the source database size and current Git revision;
- choose explicit absolute paths for the uncompressed snapshot, compressed
  artifact, restore target, and designated backup destination; and
- do not delete or overwrite any existing recovery point.

Read-only crawler state:

```bash
.venv/bin/bughouse-explorer crawl status --json
```

The uncompressed backup and restore drill each need roughly the size of the
live database. Compression temporarily requires additional space as well. Stop
before backup creation if the selected volumes do not have a safe margin.

### 2. Create a consistent snapshot

Use SQLite's online backup operation so the destination is a consistent
database snapshot:

```bash
sqlite3 data/crawler.db \
  ".backup '/absolute/backup/path/crawler-post-qualification-YYYYMMDD.db'"
```

Do not use a raw `cp` of the live database while WAL/SHM state may exist. Do not
write the backup over `data/crawler.db` or an earlier recovery artifact.

### 3. Verify the uncompressed snapshot

Open the backup, not the live database, and record:

```bash
sqlite3 /absolute/backup/path/crawler-post-qualification-YYYYMMDD.db \
  "PRAGMA quick_check;"

sqlite3 /absolute/backup/path/crawler-post-qualification-YYYYMMDD.db \
  "SELECT COUNT(*) FROM pragma_foreign_key_check;"
```

The required results are `ok` and `0`. Also compare at least:

- schema migration versions;
- games and participant rows;
- player states and permanent-tracking count;
- completed crawls and terminal outcomes;
- jobs by state and crawl-event count;
- qualification-invariant violations;
- fixed-window violations; and
- closure readiness.

Any discrepancy must be explained before compression or backup copying.

The repository-local `scripts/validate_crawler_recovery.sql` records these
checks for the current fixed bootstrap evaluation window. For a cold snapshot:

```bash
sqlite3 \
  'file:/absolute/backup/path/crawler-post-qualification-YYYYMMDD.db?mode=ro&immutable=1' \
  ".read scripts/validate_crawler_recovery.sql"
```

Review its fixed-window constants before using it for a future policy window.

### 4. Compress and checksum

Compress the checked snapshot without changing the source:

```bash
zstd -T0 /absolute/backup/path/crawler-post-qualification-YYYYMMDD.db \
  -o /absolute/backup/path/crawler-post-qualification-YYYYMMDD.db.zst

zstd --test \
  /absolute/backup/path/crawler-post-qualification-YYYYMMDD.db.zst

shasum -a 256 \
  /absolute/backup/path/crawler-post-qualification-YYYYMMDD.db.zst
```

Record the uncompressed and compressed sizes, elapsed time, Zstandard version,
and compression command. A smaller file alone is not verification.

### 5. Restore to a separate path

Choose a restore volume with enough space, then decompress without overwriting
the source or backup:

```bash
zstd -d /absolute/backup/path/crawler-post-qualification-YYYYMMDD.db.zst \
  -o /absolute/restore/path/restored-crawler.db
```

Compare the SHA-256 of the original uncompressed snapshot and restored file.
Then repeat `quick_check`, the foreign-key scan, core counts, qualification
checks, and closure audit against the restored path.

The restore test is not complete if only `zstd --test` succeeds. SQLite must
open and validate the decompressed database.

### 6. Copy to the designated backup directory and restore from that copy

The operator must choose and authorize the backup destination. Copy the
compressed artifact and a small manifest containing its checksum and restore
instructions. Verify the checksum at the destination.

The drill reads back the designated copy, restores it to a disposable local
path, and repeats the database validation. Merely completing the copy does not
prove recoverability.

### 7. Publish the recovery record

Update the handoff with:

- snapshot timestamp and the point in crawler history it represents;
- source, compressed, restored, and backup sizes/locations;
- SHA-256 checksum;
- exact restore command;
- `quick_check`, foreign-key, count, invariant, and closure results;
- whether the restore was performed from the designated backup copy;
- any retained older recovery points; and
- the next scheduled drill or rotation decision.

Do not delete the prior snapshot or temporary restored copy without resolving
the exact paths and obtaining any required cleanup authority.

## Recovery priorities

1. Continue placing verified compressed snapshots and manifests in the
   designated `/Users/aronteh/Desktop/Coding_Adventures/bughouse` directory.
2. Periodically restore from that designated copy and rerun database validation.
3. Retain enough recovery history to survive a bad monthly update being noticed
   after the newest backup.
4. Revisit physically independent/off-host storage only if the accepted threat
   model changes.
5. Consider rotation or storage-reduction experiments only after a newer
   checked snapshot exists.

## Full opening-tree build input contract

The full-tree scale-up must not read from or build directly against
`data/crawler.db`. Before authorizing the writer, select an explicit separate
restored snapshot and record:

- absolute source path outside the live database path;
- manifest and compressed/uncompressed SHA-256 values;
- proof that the bytes came from the designated backup copy where applicable;
- successful decompression/read-back comparison and SQLite `quick_check`;
- foreign-key, closure, count, and invariant results;
- accepted-game count observed by the opening adapter;
- free space for the restored source, temporary writer state, final immutable
  artifact, validation/rebuild evidence, and rollback headroom; and
- the exact output directory, which must not be the representative artifact.

If no current snapshot meets that contract, the full build is blocked pending
a new checked backup/restore cycle. Do not silently substitute the live
database or an unverified copy.

The produced full artifact is derived and rebuildable, not a replacement raw
backup. Publish it as a new immutable version with its own component checksums,
build/source fingerprints, format/adapter/terminal-policy versions, timing and
resource record, correction procedure, and deletion record. Retain the
validated representative artifact as the correctness oracle and immediate
service rollback until the full version has passed local and hosted validation.

The SQLite online-backup behavior is documented at
<https://www.sqlite.org/backup.html>. Per-table and per-index storage evidence
can be measured read-only with `dbstat` as documented at
<https://www.sqlite.org/dbstat.html>.
