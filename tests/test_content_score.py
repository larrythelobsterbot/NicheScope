"""_calc_content_score reads content_trends and interprets YouTube signals."""
import math
import sqlite3


def test_content_score_from_content_trends(temp_db, monkeypatch):
    from migrate_002_content_trends import migrate
    migrate(temp_db)

    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row  # _calc_content_score uses row["n"] etc.
    conn.execute(
        "INSERT INTO keywords (id, keyword, category, is_active) VALUES (99, 'acme', 'beauty', 1)"
    )
    conn.execute(
        """INSERT INTO content_trends
               (keyword_id, source, collected_at,
                video_count_7d, video_count_30d,
                total_views_30d, top_video_views,
                avg_views_per_video, raw_json)
           VALUES (99, 'youtube', datetime('now'), 5, 10, 1000000, 500000, 100000, '{}')"""
    )
    conn.commit()

    from analyzer import _calc_content_score
    score = _calc_content_score(conn.cursor(), "beauty")
    conn.close()

    # 1M total views over 10 videos = 100k avg → log10(100000)=5 → (5-3)*20 = 40
    # Plus 7-day velocity bonus. Expect score in [30, 100].
    assert 30 <= score <= 100


def test_content_score_defaults_without_data(temp_db):
    from migrate_002_content_trends import migrate
    migrate(temp_db)

    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO keywords (keyword, category, is_active) VALUES ('x', 'beauty', 1)"
    )
    conn.commit()

    from analyzer import _calc_content_score
    score = _calc_content_score(conn.cursor(), "beauty")
    conn.close()
    assert 0 <= score <= 100
