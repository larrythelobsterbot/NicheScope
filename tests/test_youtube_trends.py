"""Integration test for YouTube collector against the real API."""
import sqlite3

import pytest

from conftest import require_env


def test_collect_youtube_writes_content_trends(temp_db, monkeypatch):
    """With YOUTUBE_API_KEY set, one keyword should produce >=1 content_trends row."""
    require_env("YOUTUBE_API_KEY")

    # Apply migration so content_trends exists
    from migrate_002_content_trends import migrate
    migrate(temp_db)

    # Seed one keyword
    conn = sqlite3.connect(temp_db)
    conn.execute(
        "INSERT INTO keywords (keyword, category, is_active) VALUES (?, ?, 1)",
        ("press on nails", "beauty"),
    )
    conn.commit()
    conn.close()

    from youtube_trends import collect_youtube_trends
    success, items, err = collect_youtube_trends(budget_override=1)
    assert success is True, f"collector failed: {err}"
    assert items >= 1

    conn = sqlite3.connect(temp_db)
    rows = conn.execute(
        "SELECT source, total_views_30d FROM content_trends"
    ).fetchall()
    conn.close()
    assert rows, "no content_trends rows written"
    assert all(r[0] == "youtube" for r in rows)
    assert all(r[1] is not None for r in rows)


def test_collect_youtube_returns_failure_without_key(temp_db, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    from migrate_002_content_trends import migrate
    migrate(temp_db)

    import importlib
    import config
    importlib.reload(config)
    import youtube_trends
    importlib.reload(youtube_trends)

    success, items, err = youtube_trends.collect_youtube_trends(budget_override=1)
    assert success is False
    assert items == 0
    assert "YOUTUBE_API_KEY" in (err or "")
