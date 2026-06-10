"""Tests for breakout alert floor, dedup, expiry, and collector stall guard."""
import sqlite3

import pytest


@pytest.fixture
def stall_db(temp_db, monkeypatch):
    """temp_db with collector_health fully migrated and scheduler pointed at it."""
    from migrate_002_content_trends import migrate as migrate_002
    from migrate_003_stall_guard import migrate as migrate_003
    migrate_002(temp_db)
    migrate_003(temp_db)

    import scheduler
    monkeypatch.setattr(scheduler, "DB_PATH", temp_db)
    monkeypatch.setattr(scheduler, "send_telegram", lambda *a, **k: None)
    return temp_db


def _db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _seed_keyword(db_path, keyword, category, scores):
    """Insert a keyword with weekly trend points, oldest first."""
    conn = _db(db_path)
    cur = conn.execute(
        "INSERT INTO keywords (keyword, category, is_active) VALUES (?, ?, 1)",
        (keyword, category),
    )
    kid = cur.lastrowid
    for i, score in enumerate(scores):
        conn.execute(
            """INSERT INTO trend_data (keyword_id, date, interest_score)
               VALUES (?, date('now', ?), ?)""",
            (kid, f"-{(len(scores) - 1 - i) * 7} days", score),
        )
    conn.commit()
    conn.close()
    return kid


def test_breakout_requires_min_interest(temp_db):
    import analyzer

    # Both spike +100% over 4 weeks, but only one clears the interest floor
    _seed_keyword(temp_db, "noise kw", "beauty", [2, 2, 2, 2, 4])
    _seed_keyword(temp_db, "real kw", "beauty", [30, 30, 30, 30, 60])

    breakouts = analyzer.detect_breakouts()
    keywords = [b["keyword"] for b in breakouts]
    assert "real kw" in keywords
    assert "noise kw" not in keywords


def test_generate_alerts_dedups_within_window(temp_db):
    import analyzer

    breakout = {
        "keyword": "pdrn serum",
        "category": "beauty",
        "velocity_4w": 120.0,
        "velocity_12w": 200.0,
        "current_interest": 80,
        "severity": "warning",
    }

    first = analyzer.generate_alerts([dict(breakout)])
    assert len(first["new_breakouts"]) == 1
    assert first["new_breakouts"][0]["is_new"] is True

    second_breakout = dict(breakout)
    second = analyzer.generate_alerts([second_breakout])
    assert second["new_breakouts"] == []
    assert second_breakout["is_new"] is False

    conn = _db(temp_db)
    count = conn.execute(
        "SELECT COUNT(*) FROM alerts WHERE type = 'breakout'"
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_price_alerts_dedup_by_asin(temp_db):
    import analyzer

    anomaly = {
        "type": "price_drop",
        "asin": "B0TEST123",
        "title": "Test Serum",
        "category": "beauty",
        "drop_pct": 20.0,
        "current_price": 9.99,
        "prev_price": 12.99,
    }
    first = analyzer.generate_alerts([], [dict(anomaly)])
    second = analyzer.generate_alerts([], [dict(anomaly)])
    assert len(first["new_price_alerts"]) == 1
    assert second["new_price_alerts"] == []


def test_expire_old_alerts(temp_db):
    import analyzer

    conn = _db(temp_db)
    conn.execute(
        """INSERT INTO alerts (type, severity, message, data, sent_at, acknowledged)
           VALUES ('breakout', 'info', 'old', '{}', datetime('now', '-45 days'), 0)"""
    )
    conn.execute(
        """INSERT INTO alerts (type, severity, message, data, sent_at, acknowledged)
           VALUES ('breakout', 'info', 'recent', '{}', datetime('now', '-1 day'), 0)"""
    )
    conn.commit()
    conn.close()

    expired = analyzer.expire_old_alerts()
    assert expired == 1

    conn = _db(temp_db)
    unread = conn.execute(
        "SELECT message FROM alerts WHERE acknowledged = 0"
    ).fetchall()
    conn.close()
    assert [r["message"] for r in unread] == ["recent"]


def test_stall_guard_alerts_after_threshold(stall_db):
    temp_db = stall_db
    import scheduler

    # 5 consecutive successful runs writing zero rows -> stall alert
    for _ in range(scheduler.STALL_THRESHOLD):
        scheduler.run_collector_job("keepa", lambda: (True, 0, None))

    conn = _db(temp_db)
    alerts = conn.execute(
        "SELECT * FROM alerts WHERE type = 'collector_stalled'"
    ).fetchall()
    conn.close()
    assert len(alerts) == 1
    assert "keepa" in alerts[0]["message"]

    # Further zero runs within the dedup window do not re-alert
    scheduler.run_collector_job("keepa", lambda: (True, 0, None))
    conn = _db(temp_db)
    count = conn.execute(
        "SELECT COUNT(*) FROM alerts WHERE type = 'collector_stalled'"
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_stall_counter_resets_on_real_rows(stall_db):
    temp_db = stall_db
    import scheduler

    for _ in range(scheduler.STALL_THRESHOLD - 1):
        scheduler.run_collector_job("youtube", lambda: (True, 0, None))
    scheduler.run_collector_job("youtube", lambda: (True, 42, None))
    scheduler.run_collector_job("youtube", lambda: (True, 0, None))

    conn = _db(temp_db)
    row = conn.execute(
        "SELECT consecutive_zero_runs FROM collector_health WHERE collector_name = 'youtube'"
    ).fetchone()
    stalls = conn.execute(
        "SELECT COUNT(*) FROM alerts WHERE type = 'collector_stalled'"
    ).fetchone()[0]
    conn.close()
    assert row["consecutive_zero_runs"] == 1
    assert stalls == 0


def test_skip_reason_does_not_count_as_stall(stall_db):
    temp_db = stall_db
    import scheduler

    # Zero rows with an explicit skip reason (e.g. API key not set) is not a stall
    for _ in range(scheduler.STALL_THRESHOLD + 1):
        scheduler.run_collector_job("alibaba", lambda: (True, 0, "API key not set"))

    conn = _db(temp_db)
    stalls = conn.execute(
        "SELECT COUNT(*) FROM alerts WHERE type = 'collector_stalled'"
    ).fetchone()[0]
    conn.close()
    assert stalls == 0
