# Copy-ready prompt — backup and recovery hygiene slice

Use the following prompt to begin the next operational session.

---

We are continuing work in:

```text
/Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer
```

Start by reading, in order:

1. `docs/README.md`
2. `docs/HANDOFF_2026-08-01.md`
3. `docs/BACKUP_RECOVERY.md`
4. `docs/PLATFORM_ARCHITECTURE.md`

Our immediate goal is to establish a fresh, post-qualification-reconciliation
database recovery point and prove that it can be restored. This is a backup and
recovery slice, not a live-storage compression experiment.

Verified starting state:

- `data/crawler.db` is the lossless live source of truth.
- The durable queue is empty and closure is ready.
- There are 1,013 eligible/permanently tracked players, 1,153 dormant players,
  and 245,108 candidates.
- There are 8,195,984 games and 16,391,968 participant rows.
- Qualification and fixed-window invariant scans have zero violations.
- `data/crawler-final-20260801.db.zst` is a checked local recovery artifact, but
  it predates the later 86-row qualification reconciliation.
- The existing snapshot checksum and restore instructions are recorded in the
  handoff.
- No off-host restore workflow has yet been verified.

Strict boundaries:

- Do not initiate Chess.com requests, a monthly crawl, or any crawler work.
- Do not mutate `data/crawler.db`, its schema, normalized values, or raw
  payloads.
- Do not experiment with row-level compression, compressed SQLite VFSs,
  integer-key migrations, binary UUIDs/hashes, or column removal.
- Zstandard is authorized only for the new cold backup artifact. The database
  must be restored to ordinary SQLite bytes before it is queried.
- Do not overwrite or delete the existing `.zst` recovery point.
- Do not delete temporary snapshots or restores without resolving their exact
  paths and obtaining any required cleanup authority.
- Preserve unrelated working-tree changes.

Required workflow:

1. Confirm no crawler process, run, lease, or durable work is active.
2. Record current status, Git revision, source size, filesystem free space, and
   the exact proposed backup/restore paths.
3. If no off-host destination is already configured and discoverable, ask for
   that destination before attempting an external copy. Continue with the
   local backup and restore drill if it is safe to do so.
4. Use SQLite's online `.backup` operation to create a new snapshot at a
   separate explicit path.
5. Validate the uncompressed snapshot with:
   - `PRAGMA quick_check`;
   - a complete foreign-key scan;
   - schema migration equality;
   - games, participants, players, jobs, events, and terminal-outcome counts;
   - qualification and fixed-window invariants; and
   - closure readiness.
6. Compress only that checked snapshot with Zstandard. Record the exact command,
   tool version, elapsed time, source/compressed bytes, and SHA-256 checksum.
7. Run `zstd --test` on the compressed artifact.
8. Decompress it to a different explicit path with enough free space.
9. Prove that the restored bytes match the checked uncompressed snapshot, then
   repeat SQLite integrity, count, invariant, and closure checks against the
   restored path.
10. Copy the compressed artifact and checksum manifest off-host only after the
    user has authorized the exact destination. Verify the checksum at that
    destination and, where practical, perform the final restore drill from the
    off-host copy.
11. Update `docs/HANDOFF_2026-08-01.md` and `docs/BACKUP_RECOVERY.md` with the
    demonstrated artifact path, checksum, sizes, restoration evidence,
    destination, and any remaining recovery gap.
12. Review the complete diff and run `git diff --check`. Do not commit or push
    unless explicitly requested in that session.

Stop and report before proceeding if:

- any active crawler work appears;
- free space is insufficient for both the snapshot and restore drill;
- a live/source path would be overwritten;
- the new snapshot differs unexpectedly from the source state;
- `quick_check`, foreign keys, counts, qualification invariants, or closure
  fail;
- the compressed checksum changes after copying; or
- the only way forward requires deleting a recovery artifact.

Definition of done:

- a fresh post-reconciliation SQLite snapshot exists;
- a Zstandard-compressed copy passes `zstd --test`;
- its SHA-256 and exact restore command are documented;
- a separate decompressed restore opens and passes all database checks;
- an off-host checksum has been verified, or the missing destination is
  explicitly reported as the sole remaining blocker; and
- no crawler, live database, or application data was mutated.

Keep demonstrated results separate from assumptions. The purpose is proven
recoverability, not merely producing another compressed file.

---
