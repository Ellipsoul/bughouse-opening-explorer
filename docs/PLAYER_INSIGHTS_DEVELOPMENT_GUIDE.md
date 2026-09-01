# Player Insights development and refresh guide

This document is the canonical contract for adding a Player Insight to the
`bughouse-opening-explorer` data platform and publishing its browser-safe
projection in `bughouse-chess`.

Read this guide before changing either repository. Then use
[`PLAYER_INSIGHTS_SESSION_PROMPT.md`](PLAYER_INSIGHTS_SESSION_PROMPT.md) to
start a focused implementation session. The completed material experiment in
[`PLAYER_MATERIAL_INSIGHTS_RESULT_2026-08-05.md`](PLAYER_MATERIAL_INSIGHTS_RESULT_2026-08-05.md)
is the first proven reference implementation. The shared-pass Average King
Height extension and its score-8 evidence boundary are recorded in
[`PLAYER_KING_HEIGHT_INSIGHTS_RESULT_2026-08-06.md`](PLAYER_KING_HEIGHT_INSIGHTS_RESULT_2026-08-06.md).
The colour-aware drop-square extension, static-size decision, and responsive
comparison UI are recorded in
[`PLAYER_DROP_HEATMAP_INSIGHTS_RESULT_2026-08-09.md`](PLAYER_DROP_HEATMAP_INSIGHTS_RESULT_2026-08-09.md).
The bounded top-three single-game material extension and its static final-board
UI are recorded in
[`PLAYER_MATERIAL_GAME_HIGHS_INSIGHTS_RESULT_2026-08-12.md`](PLAYER_MATERIAL_GAME_HIGHS_INSIGHTS_RESULT_2026-08-12.md).

## What counts as a Player Insight

A Player Insight is a reproducible statistic about the permanently tracked
player cohort, derived from a named immutable crawler snapshot, stored with its
provenance in a versioned SQLite artifact, and exported as the smallest
browser-safe static projection needed by its UI.

The UI shape is deliberately not part of the definition. An insight may be a
leaderboard, distribution, comparison, timeline, profile card, or another
purpose-built view. Consistency belongs in the source, semantics, provenance,
build, validation, and publication contracts—not in forcing every insight into
one table.

## Current proven baseline

The current local artifact contains four feature-owned insights built in one
source pass because they share cohort, eligibility, complete-replay, and
denominator semantics:

- `bughouse_explorer/insights/material.py` performs one source scan and builds
  a versioned Player Insights database containing material aggregates, eight
  king-height buckets per player, sparse score-8 evidence, colour-specific game
  denominators, exact piece-drop counts for every colour/piece/square, and only
  the three greatest positive and negative single-game material results per
  player and piece-value preset;
- `scripts/build_player_insights.py` verifies the source snapshot checksum and
  writes a build result;
- `bughouse_explorer/insights/export.py` creates deterministic static JSON;
- `scripts/export_player_insights.py`,
  `scripts/export_king_height_insights.py`, and
  `scripts/export_drop_heatmap_insights.py`, and
  `scripts/export_material_game_highs.py` verify the derived database checksum
  and can explicitly replace their checked frontend projections;
- `tests/test_material_insights.py` and
  `tests/test_player_insights_export.py` cover capture semantics, malformed TCN,
  cohort expansion, provenance, determinism, and safe export; and
- `bughouse-chess/app/player-insights/` and
  `bughouse-chess/app/components/player-insights/` render the static data, with
  the larger king-height, drop, and material-game-high projections isolated in
  their lazy-loaded insight chunks.

This is a proven four-insight vertical slice, not yet a generic insight-plugin
framework.
A new implementation should reuse its contracts and shared primitives where
they fit, but it must not claim that a general orchestrator, generic schema, or
incremental refresh mechanism already exists.

## Architecture and ownership

```text
named immutable crawler snapshot + verified SHA-256
                         |
                         v
versioned analyzers and explicit eligibility policies
                         |
                         v
versioned, immutable Player Insights SQLite artifact
                         |
                         v
validated deterministic browser projection(s)
                         |
                         v
bughouse-chess build-time import + feature-owned renderer
```

`bughouse-opening-explorer` owns:

- source-snapshot selection and checksum verification;
- cohort, game-eligibility, denominator, replay, and anomaly policies;
- efficient aggregation and derived SQLite schemas;
- analyzer, schema, and dataset versioning;
- deterministic browser-safe export; and
- extraction, integrity, and refresh evidence.

`bughouse-chess` owns:

- the checked static projection and its TypeScript contract;
- the insight registry/chips and each insight's renderer;
- search, sorting, filtering, pagination, responsive layout, and accessibility;
- user preferences that affect presentation, such as piece-value presets; and
- route, component, lint, build, and browser verification.

The browser must not receive `crawler.db`, a restored raw snapshot, the derived
SQLite artifact, raw TCN, or an anomaly corpus. At the current cohort size, the
default publication mechanism is a checked static file imported at build time;
there is no runtime insights service.

## Specify the insight before implementing it

Every insight needs a written contract. Resolve all of the following before a
full extraction:

1. **Question and user value** — the exact question the UI answers.
2. **Stable identifier and label** — a code-safe ID and user-facing name.
3. **Grain** — for example, one row per player, player and month, or player
   pair. Avoid silently calling a non-player grain a player metric.
4. **Cohort** — normally every row in `players` whose
   `tracking_started_at IS NOT NULL`. Never hard-code the current cohort size.
5. **Eligible games** — the accepted source games that may contribute, plus any
   further filters and the reason for each filter.
6. **Denominator** — analyzed games, eligible games, appearances, rounds,
   opportunities, time, or another explicit quantity. Define zero-denominator
   behavior.
7. **Contribution semantics** — exact event-to-player attribution, team/board
   behavior, signs, ties, nulls, rounding, and units.
8. **Malformed-data policy** — whether a failure excludes the whole game or a
   safely independent part. State how the failure is counted and classified.
9. **Source fields and replay needs** — prefer existing normalized columns when
   sufficient; replay TCN only when the insight genuinely depends on moves.
10. **Privacy and publication** — identify exactly which aggregate fields the
    browser needs. Exclude raw evidence and operational detail by default.
11. **Expected UI shape** — leaderboard, chart, cards, profile detail, or
    something else, including search/filter/sort expectations.
12. **Acceptance examples** — tiny deterministic games or records with exact
    expected output, including at least one important edge case.

If any definition would materially change the statistic, stop and resolve it
with the user rather than burying the choice in code.

## Cohort and source rules

The default cohort is permanently tracked players selected from the snapshot:

```sql
SELECT ...
FROM players
WHERE tracking_started_at IS NOT NULL
```

This automatically includes players enrolled after the first 1,013-player
build. Display names may be retained, but matching and aggregation must use the
repository's normalized player identity rules.

Build only from a named, checked, immutable snapshot produced by the documented
monthly recovery/release workflow. Open it read-only and immutable. Never run a
multi-minute analytics scan against the live `data/crawler.db`, and never
modify, migrate, vacuum, or otherwise optimize the source snapshot in place.

Record at minimum:

- source path or stable snapshot name;
- exact source SHA-256;
- source dataset counts needed to reconcile the run;
- cohort policy and version;
- adapter/replay policy and version;
- each analyzer version;
- output schema version;
- start/end timestamps and elapsed time; and
- accepted, analyzed, excluded, and otherwise skipped counts with explicit
  meanings.

## Extraction design

### Scan once, attribute many times

Millions of games are manageable when each eligible source game is visited
once. Do not issue one lifetime query or replay pass per player. Resolve the
tracked participants for a game, compute its contribution once, and update all
affected player aggregates.

When several new insights share the same cohort, source eligibility, and replay
requirements, prefer one coordinated source pass with independent accumulators.
Do not combine analyzers whose failure or eligibility policies differ merely to
save a scan; the semantic contract is more important than a small speedup.

Prefer streaming iteration and bounded in-memory state. With roughly thousands
of players, fixed-size per-player accumulators are appropriate. Avoid retaining
millions of game records or events in memory unless a benchmark demonstrates
that it is necessary and safe.

### Treat each game atomically by default

An accepted game that cannot be fully interpreted must not leave partial
contributions behind. Compute into temporary game-local state and merge it only
after the game passes the analyzer's validation. Record a stable, bounded
anomaly reason and continue the build.

The material implementation demonstrates why this matters: some accepted TCN
strings contain a literal `undefined` tail or otherwise stop replaying legally.
Those games are counted as replay-excluded and contribute no prefix captures.
Other insights that do not depend on move replay may still be able to use the
same source game; eligibility is insight-specific and must be named precisely.

Partial acceptance is allowed only when the insight contract proves the parts
are independent, tests the boundary, and exposes separate denominators.

### Keep domain edge cases with the analyzer

Rules such as “capturing a promoted piece counts as capturing a pawn” and
“capturing a dropped piece uses the dropped piece's full type” belong to the
material analyzer. Do not promote a feature-specific rule into a global
analytics assumption. Each new insight must enumerate and test its own domain
edge cases.

### Version behavior, not just files

Increment an analyzer or policy version whenever a change can alter output.
Dataset identity must be derived from the source checksum and every semantic
version that affects the result. A code refactor that is demonstrated to be
byte-identical need not invent a new semantic version, but its equivalence must
be tested.

## Derived SQLite contract

The long-term default is one versioned Player Insights SQLite artifact per
source snapshot, with common provenance/cohort tables and feature-owned insight
tables. This keeps many small insights queryable together without coupling
their schemas.

The first `material-insights.db` remains a compatible reference artifact. The
Average King Height build demonstrates a shared `player-insights.db` without
breaking the recorded material exporter. Piece Drop Heat Maps demonstrates how
the same pass can add raw colour channels and a frontend-only normalized view
without changing earlier aggregates. Future insights should extend that pattern
only when their semantic contracts genuinely permit a shared pass.

A shared artifact should provide:

- a build/provenance table containing the source checksum and semantic
  versions;
- one canonical tracked-player table keyed by normalized identity;
- clearly named denominator/count tables when several insights share them;
- one or more tables per insight, with primary keys and foreign keys;
- SQL constraints for non-negative counts and other true invariants;
- views for exact deterministic derivations that are useful to operators; and
- bounded anomaly summaries, with detailed evidence retained only locally when
  needed for diagnosis.

Store raw counts or exact integer numerators whenever possible. Compute ratios
from named denominators and document rounding at the publication layer. Avoid
persisting presentation strings, colors, icons, ranks, or user preference
choices in SQLite.

Each build creates a new output path and refuses to overwrite an existing
artifact. Rebuild wholesale from the immutable snapshot. The current system
has no general incremental analytics updater; do not add one without defining
late corrections, deletions, policy changes, replay failures, and idempotency.

## Static publication contract

Export only the aggregate fields required by the frontend. A projection should:

- include a schema version and dataset/provenance metadata;
- name denominator fields unambiguously;
- use deterministic key order, row order, number representation, and newline;
- validate cardinality, required subrows, uniqueness, and invariants before
  writing;
- write to a temporary sibling, flush it, and publish atomically;
- refuse replacement unless the operator passes an explicit replacement flag;
- print or record the resulting SHA-256 and byte size; and
- be byte-identical across repeated exports from the same derived artifact.

Static delivery remains the default while the projection is small, public,
bounded by the tracked cohort, and comfortable in the application's client
bundle. Reconsider the mechanism if a projection becomes sensitive, grows
without a practical bound, makes initial page loading materially worse, or
requires user-specific/server-side queries. Do not introduce an API solely
because another insight has a different visual shape.

Larger static projections should be measured both raw and compressed and kept
behind their feature's lazy import. The 1,013-player material-game-high
projection is the largest current raw file at 2,216,498 bytes and 389,022 bytes
with deterministic `gzip -9 -n`; it is loaded only when its insight is
selected. The drop heat-map projection remains 1,822,069 bytes raw and 573,871
bytes with `gzip -9`.

## Frontend extension contract

Treat the page as an insight host, not a single universal leaderboard.

- Add an insight to a small typed registry containing its stable ID, label,
  description, and renderer.
- Give each materially different insight a feature-owned model and component.
- Reuse search, sort, pagination, metric formatting, empty states, and surface
  primitives when their behavior truly matches.
- Do not contort charts, comparisons, or profiles into the material table.
- Keep the static data import at build time and avoid fetching it again at
  runtime.
- Apply existing user preferences at presentation time when relevant; do not
  bake preference-specific values into the exported dataset unless the raw
  values cannot support the calculation.
- Show user-relevant data. Preserve exclusion/anomaly counts in metadata and
  the derived artifact, but do not add operational `+n excluded` labels to
  every row unless the user explicitly needs them.

Responsive behavior is part of the feature, not a later polish pass. All core
filters and sort buttons must remain reachable on narrow screens. Sorting
controls should wrap onto multiple rows rather than overflow horizontally.
Verify the smallest supported viewport, touch target size, focus states,
semantic names, empty search, long usernames, and the largest numeric values.

For sortable leaderboards, define the first-click direction, reverse behavior,
stable tie-breaker, and whether ranks describe the active sort. The current
material page defaults to “most won,” reverses on the second click, includes an
analyzed-games sort, and uses analyzed games for the per-game denominator.

## Test-driven implementation sequence

Work vertically and keep each layer demonstrable:

1. Write tiny source fixtures and failing tests for the metric definition,
   player attribution, denominator, and decisive edge cases.
2. Implement the smallest analyzer that passes those tests.
3. Add schema/provenance tests, cohort-expansion coverage, atomic failure
   behavior, and repeated-build determinism.
4. Add exporter contract tests, rejection tests for incomplete/invalid rows,
   checksum verification, and repeated-export determinism.
5. Run a representative benchmark before the full snapshot. Measure enough to
   catch accidental per-player scans, unbounded memory, or unnecessary replay.
6. Run the full local extraction only after the source checksum and output path
   are verified and the prompt authorizes it.
7. Add frontend model/component tests for sorting, filtering, pagination,
   preference-dependent calculations, accessibility, and narrow layout.
8. Run the repository's focused tests, full tests, lint, production build, and
   browser verification in proportion to the change.

Do not weaken malformed-data or integrity checks to make a full run complete.
If the full dataset exposes a new edge case, reduce it to a fixture, write the
failing test, fix the analyzer, and rebuild to a new output path.

## Full-build evidence

A successful result record should contain:

- snapshot name and verified SHA-256;
- artifact path, SHA-256, and size;
- source, adapter, cohort, schema, and analyzer versions;
- permanently tracked player count;
- accepted, analyzed, and excluded/skipped counts, reconciled by definition;
- anomaly counts grouped by stable reason;
- elapsed time, throughput, and peak memory when available;
- SQLite `quick_check`, foreign-key, cardinality, and invariant results;
- deterministic rebuild/export evidence;
- static projection path, SHA-256, raw size, and compressed-size estimate;
- frontend test/lint/build/browser evidence; and
- rollback instructions.

A handful of minutes is acceptable for a full rebuild. Prefer a clear,
measured single-pass implementation over premature complexity. Record the
actual duration rather than promising a fixed threshold.

## Snapshot refresh runbook

The automated operator procedure is
[`MONTHLY_DATA_AND_PLAYER_INSIGHTS_RUNBOOK.md`](MONTHLY_DATA_AND_PLAYER_INSIGHTS_RUNBOOK.md).
The steps below remain the semantic checklist enforced by that runner.

For every new completed crawler snapshot:

1. Finish the raw monthly workflow and create or restore its named immutable
   snapshot according to the existing recovery/release runbook.
2. Verify the snapshot SHA-256 and SQLite integrity before analytics work.
3. Choose a new versioned insights artifact directory. Never reuse or overwrite
   an older result.
4. Run the tested builder from the immutable snapshot, supplying the expected
   source checksum.
5. Validate SQLite integrity, foreign keys, cohort/cardinality invariants,
   denominators, anomaly reconciliation, representative player queries, and
   deterministic output.
6. Export each browser projection from the verified derived database. Review
   its metadata and checksum before explicitly replacing the checked frontend
   file.
7. Update or create a dated result record with the evidence listed above.
8. Run extraction/export tests and the affected `bughouse-chess` tests, lint,
   production build, and responsive browser checks.
9. Review both worktrees. Commit, push, Preview, or Production deployment remain
   explicit operator actions unless separately authorized.

The browser projection is the release switch. Rolling back the public insight
means reverting the checked projection and affected frontend code, then
redeploying. Retain earlier immutable derived artifacts so a release can be
reproduced and compared.

## Choosing the scope of a new insight

Extend the existing derived build when the new insight:

- uses the same immutable snapshot and permanently tracked cohort;
- can share the same source scan or replay without weakening semantics;
- belongs to the same refresh and publication event; and
- remains a compact public aggregate.

Use a separate analyzer pass, table family, projection, or artifact when it has
a different eligibility policy, grain, denominator, security boundary, update
cadence, or operational risk. Sharing a page does not require sharing a table;
sharing a database does not require sharing an analyzer.

## Definition of done

A new Player Insight is complete only when:

- its semantic contract and edge cases are written;
- future permanently tracked players are included without a code change;
- the source snapshot and all output versions/checksums are recorded;
- malformed data is handled atomically and audibly;
- the derived data is queryable in SQLite and validated by tests;
- the browser projection is minimal, deterministic, validated, and static;
- its UI is appropriate to the insight and works on narrow and wide screens;
- extraction, export, frontend tests, lint, build, and browser checks pass;
- the refresh procedure and rollback are documented; and
- no raw database, TCN, private evidence, or operational credential reaches the
  browser.

## Anti-patterns

Do not:

- query or mutate the live crawler database for an analytics build;
- hard-code 1,013 players or any other snapshot count;
- scan the full game corpus once per player;
- keep prefix results from a game that later fails atomic replay validation;
- silently discard malformed records or erase their aggregate provenance;
- overwrite a derived database or static projection implicitly;
- compute raw-game analytics in the browser;
- expose the derived SQLite artifact as a downloadable frontend asset;
- force every insight into the same table or interaction model;
- display backend anomaly bookkeeping as row-level clutter by default;
- add a runtime service before static size or query needs justify it; or
- commit, push, deploy, create paid resources, or alter Production without the
  user's explicit authorization.
