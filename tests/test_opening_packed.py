from bughouse_explorer.opening.model import QueryFilter
from bughouse_explorer.opening.packed import PackedIndex, build_packed_index
from bughouse_explorer.opening.relational import RelationalIndex, build_relational_index
from opening_fixtures import E4, E5, corpus, game


def test_packed_sorted_postings_match_relational_query_contract(tmp_path):
    games = corpus()
    relational_path = tmp_path / "relational.sqlite3"
    packed_path = tmp_path / "packed"
    build_relational_index(games, relational_path, source_fingerprint="fixture-v1")
    build_packed_index(
        games, packed_path, source_fingerprint="fixture-v1", postings="sorted"
    )
    queries = [
        ((), None),
        ((E4,), None),
        ((E4, E5), None),
        ((), QueryFilter(white_username="carol")),
        ((), QueryFilter(black_username="yara")),
        (
            (E4,),
            QueryFilter(white_username="alice", black_username="xavier"),
        ),
    ]

    with RelationalIndex(relational_path) as relational, PackedIndex(packed_path) as packed:
        for prefix, query_filter in queries:
            assert packed.query(prefix, query_filter) == relational.query(
                prefix, query_filter
            )


def test_compressed_bitmap_postings_match_sorted_ordinal_queries(tmp_path):
    games = corpus()
    sorted_path = tmp_path / "sorted"
    bitmap_path = tmp_path / "bitmap"
    build_packed_index(
        games, sorted_path, source_fingerprint="fixture-v1", postings="sorted"
    )
    build_packed_index(
        games, bitmap_path, source_fingerprint="fixture-v1", postings="bitmap"
    )
    queries = [
        ((), QueryFilter(white_username="alice")),
        ((), QueryFilter(black_username="xavier")),
        (
            (E4,),
            QueryFilter(white_username="alice", black_username="xavier"),
        ),
    ]

    with PackedIndex(sorted_path) as sorted_index, PackedIndex(bitmap_path) as bitmap:
        for prefix, query_filter in queries:
            assert bitmap.query(prefix, query_filter) == sorted_index.query(
                prefix, query_filter
            )


def test_packed_single_game_is_terminal_at_the_root(tmp_path):
    artifact = tmp_path / "packed"
    build_packed_index(
        [game("only", (E4, E5))],
        artifact,
        source_fingerprint="single",
        postings="sorted",
    )

    with PackedIndex(artifact) as index:
        root = index.query(())

    assert root.support == 1
    assert root.sole_game_uuid == "only"
    assert root.branches == ()
