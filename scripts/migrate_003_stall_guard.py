"""
Migration 003: Add consecutive_zero_runs to collector_health.

Tracks successful collector runs that wrote zero rows so the scheduler can
detect silently-stalled collectors (success status, no data — e.g. Keepa
running against an unseeded products table for months).

Safe to run multiple times.
"""

import sqlite3
import os

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "nichescope.db")
)


def migrate(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        conn.execute(
            "ALTER TABLE collector_health ADD COLUMN consecutive_zero_runs INTEGER DEFAULT 0"
        )
        print("Added collector_health.consecutive_zero_runs")
    except sqlite3.OperationalError:
        print("collector_health.consecutive_zero_runs already exists")
    conn.commit()
    conn.close()
    print(f"Migration 003 complete: {db_path or DB_PATH}")


if __name__ == "__main__":
    migrate()
