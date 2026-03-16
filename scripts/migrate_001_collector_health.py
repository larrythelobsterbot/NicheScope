"""
Migration 001: Add collector_health table for tracking collector reliability.
Safe to run multiple times (uses IF NOT EXISTS).
"""

import sqlite3
import os
import sys

# Resolve DB path: use env var if set, otherwise default relative to project root
DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "nichescope.db")
)


def migrate():
    if not os.path.exists(os.path.dirname(DB_PATH)):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS collector_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collector_name TEXT NOT NULL UNIQUE,
            last_run DATETIME,
            last_success DATETIME,
            last_error TEXT,
            consecutive_failures INTEGER DEFAULT 0,
            total_runs INTEGER DEFAULT 0,
            total_successes INTEGER DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print(f"Migration 001 complete: collector_health table ensured in {DB_PATH}")


if __name__ == "__main__":
    migrate()
