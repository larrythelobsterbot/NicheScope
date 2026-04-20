"""Test migration 002: content_trends schema."""
import sqlite3

from migrate_002_content_trends import migrate


def test_creates_content_trends_table(temp_db):
    migrate(temp_db)
    conn = sqlite3.connect(temp_db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(content_trends)")]
    conn.close()
    assert "keyword_id" in cols
    assert "source" in cols
    assert "total_views_30d" in cols
    assert "video_count_7d" in cols


def test_creates_tiktok_trends_view(temp_db):
    migrate(temp_db)
    conn = sqlite3.connect(temp_db)
    rows = conn.execute(
        "SELECT type FROM sqlite_master WHERE name='tiktok_trends'"
    ).fetchall()
    conn.close()
    # init_db creates tiktok_trends as a TABLE; migrate must replace it with a VIEW.
    assert any(r[0] == "view" for r in rows), f"Expected view, got {rows}"


def test_idempotent(temp_db):
    migrate(temp_db)
    migrate(temp_db)  # must not raise
    conn = sqlite3.connect(temp_db)
    cnt = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name='content_trends'"
    ).fetchone()[0]
    conn.close()
    assert cnt == 1


def test_adds_collector_health_columns(temp_db):
    migrate(temp_db)
    conn = sqlite3.connect(temp_db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(collector_health)")]
    conn.close()
    assert "items_collected" in cols
    assert "last_status" in cols
