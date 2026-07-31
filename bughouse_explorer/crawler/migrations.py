"""Numbered SQLite migrations for the standalone crawler database."""

from pathlib import Path
import sqlite3


MIGRATIONS_DIR = Path(__file__).with_name("sql")


def connect(database_path):
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def apply_migrations(database_path):
    """Apply every pending bundled migration in filename order."""
    conn = connect(database_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS crawler_schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at INTEGER NOT NULL
            )
            """
        )
        applied = {
            row[0]
            for row in conn.execute("SELECT version FROM crawler_schema_migrations")
        }
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            conn.executescript(path.read_text())
            conn.execute(
                "INSERT INTO crawler_schema_migrations(version, applied_at) "
                "VALUES (?, CAST(strftime('%s', 'now') AS INTEGER))",
                (path.name,),
            )
            conn.commit()
    finally:
        conn.close()
