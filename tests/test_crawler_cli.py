from click.testing import CliRunner

from bughouse_explorer.cli import main
from bughouse_explorer.crawler.migrations import connect


def test_crawl_migrate_and_seed_commands_initialize_the_sqlite_queue(tmp_path):
    path = str(tmp_path / "crawler.db")
    runner = CliRunner()

    migrated = runner.invoke(main, ["crawl", "--crawler-db", path, "migrate"])
    assert migrated.exit_code == 0, migrated.output

    seeded = runner.invoke(
        main, ["crawl", "--crawler-db", path, "seed", "Larso", "LARSO"]
    )
    assert seeded.exit_code == 0, seeded.output

    conn = connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM crawl_jobs").fetchone()[0] == 1
    finally:
        conn.close()
