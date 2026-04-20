#!/usr/bin/env python3
"""Migration 002: rename tiktok_trends -> content_trends with YouTube-compatible schema.

Idempotent: safe to re-run. The old tiktok_trends table (if it exists from init_db)
is dropped and replaced by a VIEW that reads from content_trends with source='youtube'.
Also extends collector_health with items_collected and last_status columns
(Track 2 will replace this table wholesale; these columns are the minimum we need
now so run_collector_job can record honest outcomes).
"""
import os
import sqlite3
import sys


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        # 1. Create the new table
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS content_trends (
                id INTEGER PRIMARY KEY,
                keyword_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                collected_at DATETIME NOT NULL,
                video_count_7d INTEGER,
                video_count_30d INTEGER,
                total_views_30d INTEGER,
                top_video_views INTEGER,
                avg_views_per_video INTEGER,
                raw_json TEXT,
                FOREIGN KEY (keyword_id) REFERENCES keywords(id)
            );
            CREATE INDEX IF NOT EXISTS idx_content_trends_keyword_date
                ON content_trends (keyword_id, collected_at DESC);
            """
        )

        # 2. If tiktok_trends is a TABLE (from init_db.py), drop it so the view can
        #    take its place. If it's already a view, drop it so we can re-create.
        row = conn.execute(
            "SELECT type FROM sqlite_master WHERE name='tiktok_trends'"
        ).fetchone()
        if row and row[0] == "table":
            conn.execute("DROP TABLE tiktok_trends")
        elif row and row[0] == "view":
            conn.execute("DROP VIEW tiktok_trends")

        # 3. (Re)create the back-compat view — widened so that legacy analyzer SQL
        #    `SELECT ... FROM tiktok_trends WHERE keyword IN (...) AND date >= date('now', '-30 days')`
        #    keeps working during the transition, before Task 9 rewrites the analyzer.
        conn.execute(
            """
            CREATE VIEW tiktok_trends AS
                SELECT ct.id,
                       ct.keyword_id,
                       k.keyword              AS keyword,
                       ct.collected_at,
                       DATE(ct.collected_at)  AS date,
                       ct.total_views_30d     AS view_count,
                       ct.video_count_30d     AS video_count,
                       0                      AS ad_count
                FROM content_trends ct
                LEFT JOIN keywords k ON k.id = ct.keyword_id
                WHERE ct.source = 'youtube'
            """
        )

        # 4. Extend collector_health with row-count/status columns (Track 2 will
        #    replace this table wholesale; these columns are the minimum we need
        #    now so run_collector_job can record honest outcomes).
        def _add_col_if_missing(table, col, ddl):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            if col not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")

        _add_col_if_missing("collector_health", "items_collected", "INTEGER DEFAULT 0")
        _add_col_if_missing("collector_health", "last_status", "TEXT")

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    db = os.environ.get("DB_PATH") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not db:
        print("Usage: python migrate_002_content_trends.py <db_path>", file=sys.stderr)
        sys.exit(1)
    migrate(db)
    print(f"Migration 002 applied to {db}")
