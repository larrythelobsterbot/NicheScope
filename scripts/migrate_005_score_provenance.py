"""
Migration 005: Add provenance column to niche_scores.

JSON object mapping each score component to "real" (computed from
collected data) or "fallback" (hardcoded category default used because
the underlying table had no data). Lets the dashboard stop presenting
constants as analysis.

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
        conn.execute("ALTER TABLE niche_scores ADD COLUMN provenance TEXT")
        print("Added niche_scores.provenance")
    except sqlite3.OperationalError:
        print("niche_scores.provenance already exists")
    conn.commit()
    conn.close()
    print(f"Migration 005 complete: {db_path or DB_PATH}")


if __name__ == "__main__":
    migrate()
