import sqlite3

from bughouse_explorer.opening.adapter import CrawlerSnapshotAdapter, SnapshotSelection


def _crawler_fixture(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE players (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL
        );
        CREATE TABLE games (
            uuid TEXT PRIMARY KEY,
            end_time INTEGER,
            time_control TEXT,
            rated INTEGER,
            rules TEXT NOT NULL,
            tcn TEXT,
            initial_setup TEXT,
            url TEXT,
            source TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            content_hash TEXT NOT NULL
        );
        CREATE TABLE game_participants (
            game_uuid TEXT NOT NULL,
            color TEXT NOT NULL,
            player_id INTEGER NOT NULL,
            rating INTEGER,
            result TEXT,
            rating_source TEXT NOT NULL,
            PRIMARY KEY (game_uuid, color)
        );
        """
    )
    connection.executemany(
        "INSERT INTO players(id, username) VALUES (?, ?)",
        [(1, "alice"), (2, "bob")],
    )
    connection.execute(
        """
        INSERT INTO games(
            uuid, end_time, time_control, rated, rules, tcn, initial_setup,
            url, source, raw_payload, content_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "game-1",
            1_700_000_000,
            "180",
            1,
            "bughouse",
            "&f",
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "https://example.invalid/game-1",
            "callback",
            "{}",
            "content-1",
        ),
    )
    connection.executemany(
        """
        INSERT INTO game_participants(
            game_uuid, color, player_id, rating, result, rating_source
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("game-1", "white", 1, 2100, "win", "callback_pgn"),
            ("game-1", "black", 2, 2050, "checkmated", "callback_pgn"),
        ],
    )
    connection.commit()
    connection.close()


def test_adapter_preserves_exact_drop_prefix_and_callback_provenance(tmp_path):
    crawler_db = tmp_path / "crawler.db"
    _crawler_fixture(crawler_db)

    outcomes = list(CrawlerSnapshotAdapter(crawler_db).iter_outcomes())

    assert len(outcomes) == 1
    game = outcomes[0].game
    assert game.uuid == "game-1"
    assert game.move_tokens == ("&f",)
    assert game.white_username == "alice"
    assert game.black_username == "bob"
    assert game.source == "callback"
    assert game.content_hash == "content-1"
    assert game.provenance_flags == ("callback_source",)


def test_adapter_reports_each_exclusion_instead_of_silently_dropping_rows(tmp_path):
    crawler_db = tmp_path / "crawler.db"
    _crawler_fixture(crawler_db)
    connection = sqlite3.connect(crawler_db)
    base = (
        1_700_000_000,
        "180",
        1,
        "bughouse",
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "public",
        "{}",
    )
    games = [
        ("empty", "", base[0], base[1], base[2], base[3], base[4], base[5], base[6]),
        ("decode", "abc", base[0], base[1], base[2], base[3], base[4], base[5], base[6]),
        ("setup", "mC", base[0], base[1], base[2], base[3], "custom", base[5], base[6]),
        ("rules", "mC", base[0], base[1], base[2], "chess", base[4], base[5], base[6]),
        ("limit", "aa" * 2_049, base[0], base[1], base[2], base[3], base[4], base[5], base[6]),
        ("participant", "mC", base[0], base[1], base[2], base[3], base[4], base[5], base[6]),
    ]
    connection.executemany(
        """
        INSERT INTO games(
            uuid, tcn, end_time, time_control, rated, rules, initial_setup,
            source, raw_payload, url, content_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'hash')
        """,
        games,
    )
    for uuid, *_ in games[:-1]:
        connection.executemany(
            """
            INSERT INTO game_participants(
                game_uuid, color, player_id, rating, result, rating_source
            ) VALUES (?, ?, ?, 2000, 'agreed', 'public')
            """,
            [(uuid, "white", 1), (uuid, "black", 2)],
        )
    connection.execute(
        """
        INSERT INTO game_participants(
            game_uuid, color, player_id, rating, result, rating_source
        ) VALUES ('participant', 'white', 1, 2000, 'win', 'public')
        """
    )
    connection.commit()
    connection.close()

    outcomes = list(CrawlerSnapshotAdapter(crawler_db).iter_outcomes())

    skipped = {outcome.skip_reason for outcome in outcomes if outcome.skip_reason}
    assert skipped == {
        "empty_tcn",
        "decode_error",
        "nonstandard_initial_setup",
        "non_bughouse_rules",
        "safety_limit",
        "participant_shape",
    }


def test_adapter_selection_is_a_deterministic_source_rowid_sample(tmp_path):
    crawler_db = tmp_path / "crawler.db"
    _crawler_fixture(crawler_db)

    outcomes = list(
        CrawlerSnapshotAdapter(crawler_db).iter_outcomes(
            SnapshotSelection(rowid_modulus=2, rowid_remainder=1)
        )
    )

    assert [outcome.source_rowid for outcome in outcomes] == [1]
