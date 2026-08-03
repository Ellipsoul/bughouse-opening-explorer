# Opening-tree architecture/prototype slice prompt

Status: completed on 3 August 2026. The evidence and selected architecture are
in
[`OPENING_TREE_ARCHITECTURE_PROTOTYPE_2026-08-03.md`](OPENING_TREE_ARCHITECTURE_PROTOTYPE_2026-08-03.md).
This file preserves the copy-ready execution contract that produced that slice.

## Execution contract

Execute the opening-tree architecture and representative-prototype slice.
Preserve `data/crawler.db` as the lossless raw source and do not make Chess.com
requests or begin a crawl. Work against an immutable checked snapshot or
disposable derived data only.

Do not assume the retained SQLite schema, FastAPI server, Python build path, or
four-field position key is the production design. Build a move-prefix trie keyed
by the exact decoded move sequence. Transpositions remain separate paths.
Replay each path to display the board. Pocket differences between games do not
split a shared move prefix; pockets may remain contextual data or bounded node
annotations. Preserve drop moves as navigable edges. Never use placement FEN to
merge or identify trie nodes.

Freeze inclusion/provenance and terminal semantics. A terminal is reached at
the first exact move prefix supported by one distinct accepted game, or at game
end. Identical complete lines may retain multiple games, and a game may end at
a node that also has continuations. Filtered views may terminate earlier when
one player's games for the selected White or Black seat have support one.

Design a format-neutral crawler adapter, then use TDD to build comparable
representative prototypes. Include a compact relational/SQLite baseline and at
least one materially different design. Explicitly evaluate sorted-radix or
Patricia construction and a prefix-interval packed trie: sort games by move
sequence, assign dense ordinals, represent every prefix as a contiguous ordinal
range, and use per-player White/Black sorted ordinal postings. Compare binary-
search/rank queries against compressed game-id bitmap postings. Consider an
embedded ordered key/value store or different build/service language if
evidence warrants it. DuckDB/Parquet may be used for offline build analysis. No
framework or storage engine is required to match the legacy application.

Before choosing prototypes, measure prefix-trie shape directly from a
deterministic read-only TCN sample and, if cheap and space-safe, the full
move-bearing corpus: unique-prefix depth, nodes by ply, branching distribution,
identical complete lines, games ending at internal nodes, and estimated savings
from interval and one-child-run compression.

Run every candidate over the same deterministic inputs and query corpus.
Measure accepted/skipped games and reasons, plies and games per second,
unique-depth distribution, nodes/edges/membership/aggregates, peak RAM,
temporary/write-amplification/final bytes, startup and cold/warm P50/P95/P99
queries, response bytes, deterministic rebuild behavior, correction handling,
atomic publication/rollback, and operational complexity. Include unfiltered,
player-as-White, player-as-Black, exact pairing, and filtered support-one cases.

Choose the simplest architecture that meets explicit targets with headroom.
Document rejected options and evidence. Preserve explicit game references at
terminals and efficient independent White/Black filtering in every viable
design.

Do not build the full corpus until the representative benchmark is validated
and its capacity implications are documented. Do not integrate the production
Next.js UI or prematurely freeze an API. Preserve unrelated changes; do not
commit or push unless requested.
