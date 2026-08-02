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
6. At least one verified copy exists outside the machine that holds the live
   database.
7. The restore command, verification evidence, artifact size, checksum,
   creation time, and storage location are documented.

Until every condition holds, the artifact is a useful copy but not a complete
recovery system.

## Current recovery state

The live database is:

```text
data/crawler.db
```

The existing checked compressed artifact is:

```text
data/crawler-final-20260801.db.zst
```

Its recorded SHA-256 is:

```text
e0fcad6e6a8b91f3cf8fb288e0abb6215b38b0adb57c9d2670f6d16245cd2d12
```

That artifact passed decompression-stream, SQLite integrity, foreign-key, and
core-count checks when it was created. It predates the later 86-row
qualification reconciliation, however, and no off-host restore has yet been
verified. Preserve it until a newer post-reconciliation artifact has completed
this entire runbook.

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
  artifact, restore target, and off-host destination; and
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

Any discrepancy must be explained before compression or off-host copying.

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

### 6. Copy off-host and restore from that copy

The operator must choose and authorize the off-host destination. Copy the
compressed artifact and a small manifest containing its checksum and restore
instructions. Verify the checksum at the destination.

The strongest drill downloads or reads back the off-host object, restores it
to a disposable local path, and repeats the database validation. Merely
receiving a successful upload response does not prove recoverability.

### 7. Publish the recovery record

Update the handoff with:

- snapshot timestamp and the point in crawler history it represents;
- source, compressed, restored, and off-host sizes/locations;
- SHA-256 checksum;
- exact restore command;
- `quick_check`, foreign-key, count, invariant, and closure results;
- whether the restore was performed from the local or off-host copy;
- any retained older recovery points; and
- the next scheduled drill or rotation decision.

Do not delete the prior snapshot or temporary restored copy without resolving
the exact paths and obtaining any required cleanup authority.

## Recovery priorities

1. Create and verify a fresh post-qualification snapshot.
2. Place the compressed artifact off-host and verify its checksum there.
3. Restore from the off-host copy and rerun database validation.
4. Retain enough recovery history to survive a bad monthly update being noticed
   after the newest backup.
5. Only then consider backup rotation or storage-reduction experiments.

The SQLite online-backup behavior is documented at
<https://www.sqlite.org/backup.html>. Per-table and per-index storage evidence
can be measured read-only with `dbstat` as documented at
<https://www.sqlite.org/dbstat.html>.
