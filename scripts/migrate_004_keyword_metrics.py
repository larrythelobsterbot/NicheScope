"""
Migration 004: Add keyword_metrics table.

One row per keyword holding the analyzer's statistically-honest trend
metrics (window-averaged velocities, z-score, year-over-year velocity,
seasonality flag, lifecycle stage). Computed by analyzer.run_analysis();
read by the frontend API routes so velocity math lives in one place.

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS keyword_metrics (
            keyword_id INTEGER PRIMARY KEY REFERENCES keywords(id),
            computed_at DATETIME,
            current_interest REAL,
            velocity_4w REAL,
            velocity_12w REAL,
            velocity_yoy REAL,          -- NULL when <13 months of history
            z_score REAL,
            is_seasonal INTEGER DEFAULT 0,
            lifecycle TEXT              -- emerging|accelerating|peaking|declining|stable
        )
    """)
    conn.commit()
    conn.close()
    print(f"Migration 004 complete: keyword_metrics ensured in {db_path or DB_PATH}")


if __name__ == "__main__":
    migrate()
