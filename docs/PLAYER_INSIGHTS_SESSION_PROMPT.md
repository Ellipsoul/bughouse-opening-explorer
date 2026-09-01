# Reusable Player Insights session prompt

Copy the prompt below into a fresh session and replace every bracketed field.
Delete optional sections that do not apply. This prompt is designed for one or
several insights that should be extracted from the same crawler snapshot.

```text
We are continuing work in these repositories:

- /Users/aronteh/Desktop/Coding_Adventures/bughouse-opening-explorer
- /Users/aronteh/Desktop/Coding_Adventures/bughouse/bughouse-chess

For this slice, we are adding or refreshing Player Insights. Read these files
in order before changing anything:

1. bughouse-opening-explorer/docs/PLAYER_INSIGHTS_DEVELOPMENT_GUIDE.md
2. bughouse-opening-explorer/docs/PLAYER_MATERIAL_INSIGHTS_RESULT_2026-08-05.md
3. bughouse-opening-explorer/docs/MONTHLY_FULL_ARTIFACT_VERCEL_RELEASE_RUNBOOK.md
4. bughouse-opening-explorer/docs/PLATFORM_ARCHITECTURE.md
5. bughouse-opening-explorer/docs/README.md
6. bughouse-chess/README.md (especially the Player Insights section)

Inspect the current implementations and both git worktrees before proposing or
editing. Preserve unrelated work. Do not assume the current material-specific
builder is already a generic plugin framework.

## Session mode and inputs

- Desired mode: [EXPLORE_AND_PLAN | IMPLEMENT_WITH_FIXTURES | FULL_LOCAL_BUILD_AND_UI]
- Full multi-minute local extraction authorized: [YES | NO]
- Source snapshot path: [ABSOLUTE_PATH_OR_TO_BE_DISCOVERED]
- Expected source SHA-256: [SHA256_OR_TO_BE_DISCOVERED]
- New derived artifact directory: [ABSOLUTE_OR_REPOSITORY_RELATIVE_PATH]
- Frontend projection path(s): [PATHS_OR_TO_BE_DESIGNED]
- Commit/push/deploy authorization: [NONE unless explicitly stated]

If the snapshot path or checksum is marked TO_BE_DISCOVERED, identify the
latest completed immutable checked snapshot and report the evidence before a
full build. Never use or mutate live data/crawler.db. Never overwrite an
existing derived artifact.

## Insight requests

Create the following insight or insights:

### Insight 1: [USER-FACING NAME]

- Stable ID: [CODE_SAFE_ID]
- User question/value: [WHAT THE USER SHOULD LEARN]
- Expected display shape: [LEADERBOARD | DISTRIBUTION | TIMELINE | CARDS |
  COMPARISON | OTHER]
- Grain: [ONE ROW PER PLAYER / PLAYER-MONTH / PLAYER-PAIR / OTHER]
- Cohort: [DEFAULT PERMANENTLY TRACKED COHORT OR EXPLICIT DIFFERENCE]
- Eligible games: [EXACT DEFINITION]
- Denominator: [EXACT FIELD/COUNT AND ZERO-DENOMINATOR BEHAVIOR]
- Contribution/attribution rules: [EXACT RULES]
- Sort, search, filter, pagination needs: [DETAILS]
- User preferences affecting presentation: [NONE OR DETAILS]
- Known data/replay edge cases: [DETAILS]
- Required browser fields: [MINIMAL AGGREGATES OR TO_BE_DESIGNED]
- Acceptance examples: [TINY INPUTS AND EXPECTED OUTPUTS]

### Insight 2: [OPTIONAL USER-FACING NAME]

[Repeat the same fields. Add or remove insight sections as needed.]

## Non-negotiable contracts

- Treat the crawler snapshot as immutable raw truth and open it read-only.
- Select the permanently tracked cohort from tracking_started_at rather than
  hard-coding the current player count, unless an insight explicitly and
  justifiably defines another cohort.
- Visit each source game once per compatible analyzer pass; do not query or
  replay lifetime games separately for every player.
- Define eligible, analyzed, excluded, and denominator counts precisely.
- By default, merge a game's contributions only after the whole game passes the
  analyzer. Malformed TCN such as a literal undefined tail must not leave
  partial prefix contributions.
- Record bounded anomaly counts and stable reasons in the derived artifact, but
  expose only user-relevant aggregate data in the browser projection.
- Version every policy/analyzer change that can alter results. Bind dataset
  identity to the source checksum and all relevant semantic versions.
- Build a new immutable SQLite artifact and deterministic static projection.
  Refuse implicit overwrite; require explicit replacement of a checked
  frontend projection.
- Keep the public page statically served at build time while the data remains
  small and public. Do not send raw SQLite, TCN, game IDs, or anomaly evidence
  to the browser.
- Let each insight have the UI shape it needs. Reuse common controls when their
  semantics match, rather than forcing every insight into one table.
- Make all primary filters and sorting controls visible and wrapping on small
  screens. Verify narrow and desktop layouts and accessibility.
- Do not commit, push, deploy, spend money, create hosted resources, or mutate
  Production without explicit authorization.

## Required working sequence

1. Audit the existing source adapter, material analyzer/builder/exporter,
   schemas, tests, static frontend contract, Player Insights registry, and UI.
2. Write back a concise specification table for every requested insight:
   grain, cohort, eligibility, denominator, attribution, anomaly policy,
   stored fields, exported fields, and UI shape. Clearly identify any decision
   that still needs user input.
3. Decide which insights can safely share one source scan and which need an
   independent analyzer. Explain this from their semantics, not only speed.
4. Add failing deterministic fixture tests before implementation. Cover player
   attribution, denominator behavior, future cohort expansion, atomic malformed
   data behavior when replay is used, and every named edge case.
5. Implement the analyzer and versioned SQLite tables with provenance,
   constraints, and deterministic output. Prefer bounded per-player state and
   a streaming single pass.
6. Add deterministic export tests and the smallest browser-safe projection.
   Validate shape/cardinality/invariants, verify checksums, and publish
   atomically only with explicit replacement.
7. Run a representative benchmark. Report estimated full runtime and memory,
   and correct any accidental per-player scans or unbounded retention.
8. If and only if full extraction is authorized above, verify the exact source
   path and SHA-256, build to the new artifact directory, validate it, export
   the checked frontend projection, and write a dated result record. If it is
   not authorized, stop after fixtures/representative evidence and provide the
   exact reviewed command for the operator.
9. Implement the feature-owned frontend renderer and add it to the insight
   registry/chips. Reuse shared search/sort/pagination primitives only when
   appropriate. Apply existing user preferences at presentation time.
10. Verify focused and full extraction/export tests, affected frontend tests,
    lint, production build, and browser behavior at narrow and wide viewports.
11. Update the documentation map, refresh procedure, result evidence, and any
    checked metadata that a future agent will need.
12. Review both worktrees and summarize only the files intentionally changed.

If a full-data edge case appears, reduce it to a fixture and fix it through a
failing test. Do not weaken validation or silently skip the evidence merely to
complete the run.

## Deliverables

- Written semantic contract for each insight.
- Tested analyzer and versioned SQLite schema/view changes.
- Provenance, anomaly reconciliation, and deterministic-build evidence.
- Tested deterministic static export with checksum and size evidence.
- Appropriate, accessible, responsive UI registered on /player-insights.
- A dated full-build result if a full build was authorized and run.
- An updated repeatable next-snapshot refresh procedure.
- Verification results and explicit remaining risks or approval gates.

## Definition of done

The work is complete only when the insight definition is unambiguous, future
permanently tracked players are included automatically, malformed data cannot
silently corrupt aggregates, SQLite and static outputs are deterministic and
traceable to the verified snapshot, the browser receives only minimal public
aggregates, the UI works at narrow and wide widths, all relevant checks pass,
and a fresh agent can repeat the update from the documentation alone.
```

## Notes for filling the prompt

- Use `EXPLORE_AND_PLAN` when the metric itself is still uncertain.
- Use `IMPLEMENT_WITH_FIXTURES` to build and benchmark safely without starting
  the full corpus scan.
- Use `FULL_LOCAL_BUILD_AND_UI` only when the source snapshot and intended
  publication target are known and the local full extraction is authorized.
- It is fine to write `TO_BE_DESIGNED` for browser fields or schema layout; the
  agent should derive them from the semantic contract. Do not leave cohort,
  eligibility, denominator, or contribution rules vague if they can change the
  meaning of the metric.
- When several requested insights share a pass, describe them in one prompt so
  the agent can design compatible accumulators. When they have different
  security boundaries or source policies, use separate sessions or explicitly
  request separate artifacts.
