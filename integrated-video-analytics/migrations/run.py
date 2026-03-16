from __future__ import annotations

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "analytics.db"
MIGRATION_SQL = Path(__file__).resolve().parent / "0001_add_tracklets_global_sql.sql"


def run_migration(db_path: Path = DB_PATH, sql_path: Path = MIGRATION_SQL) -> None:
    if not sql_path.exists():
        raise FileNotFoundError(f"Migration SQL not found: {sql_path}")
    sql_text = sql_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.executescript(sql_text)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
    print(f"Migration applied successfully on {DB_PATH}")
