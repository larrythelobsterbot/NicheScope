"""Tests for window-averaged velocity, z-score gate, YoY seasonality, lifecycle."""
import sqlite3

import pytest


@pytest.fixture(autouse=True)
def _apply_migration_004(temp_db):
    from migrate_004_keyword_metrics import migrate
    migrate(temp_db)


def _db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _seed_keyword(db_path, keyword, category, scores):
    """Insert a keyword with weekly trend points; `scores` oldest first."""
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


def _metrics(scores_newest_first):
    from analyzer import _metrics_from_scores
    return _metrics_from_scores(scores_newest_first)


# ---------- pure metric math ----------

def test_window_averaged_velocity():
    # newest first: two weeks at 60, then weeks of 30
    m = _metrics([60, 60] + [30] * 12)
    assert m["velocity_4w"] == 100.0  # mean(60,60) vs mean(30,30,30)
    assert m["velocity_12w"] == 100.0


def test_single_spike_is_dampened_by_windows():
    # One-week spike to 90 on a 30-baseline: old code said +200%
    m = _metrics([90] + [30] * 13)
    assert m["velocity_4w"] == 100.0  # mean(90,30)=60 vs 30


def test_z_score_flags_unusual_move_not_wobble():
    flat_then_spike = _metrics([60] + [30] * 12)
    assert flat_then_spike["z_score"] >= 2

    # Same +100% endpoint move, but the series always swings 15..60
    volatile = _metrics([60, 15, 60, 15, 60, 15, 60, 15, 60, 15, 60, 15, 30])
    assert volatile["z_score"] < 2


def test_yoy_requires_full_year():
    m = _metrics([60, 60] + [30] * 12)
    assert m["velocity_yoy"] is None  # only 14 weeks of history


def test_seasonal_spike_detected():
    # Spiking now vs 4 weeks ago, but identical to the same weeks last year
    series = [60, 60, 50, 40, 30, 30, 30, 30, 30, 30, 30, 30, 30]  # this year
    filler = [20] * 37
    last_year = [60, 60, 50, 40, 30, 30]  # indexes 50..55
    m = _metrics(series + filler + last_year)
    assert m["velocity_4w"] > 30
    assert m["velocity_yoy"] is not None and m["velocity_yoy"] < 15
    assert m["is_seasonal"] is True


def test_genuine_yoy_growth_not_seasonal():
    series = [80, 80, 60, 50, 40, 40, 40, 40, 40, 40, 40, 40, 40]
    filler = [20] * 37
    last_year = [20, 20, 20, 20, 20, 20]
    m = _metrics(series + filler + last_year)
    assert m["velocity_4w"] > 30
    assert m["velocity_yoy"] > 100
    assert m["is_seasonal"] is False


def test_lifecycle_stages():
    from analyzer import _classify_lifecycle
    assert _classify_lifecycle(current=15, velocity_4w=50, velocity_12w=80) == "emerging"
    assert _classify_lifecycle(current=70, velocity_4w=50, velocity_12w=80) == "accelerating"
    assert _classify_lifecycle(current=70, velocity_4w=2, velocity_12w=60) == "peaking"
    assert _classify_lifecycle(current=40, velocity_4w=-30, velocity_12w=-20) == "declining"
    assert _classify_lifecycle(current=40, velocity_4w=0, velocity_12w=5) == "stable"


# ---------- DB integration ----------

def test_compute_all_metrics_persists(temp_db):
    import analyzer

    _seed_keyword(temp_db, "riser", "beauty", [30] * 12 + [60, 60])
    _seed_keyword(temp_db, "faller", "beauty", [60] * 12 + [30, 25])

    metrics = analyzer.compute_all_metrics()
    assert len(metrics) == 2

    conn = _db(temp_db)
    rows = {
        r["lifecycle"]
        for r in conn.execute(
            "SELECT km.lifecycle FROM keyword_metrics km"
        ).fetchall()
    }
    count = conn.execute("SELECT COUNT(*) FROM keyword_metrics").fetchone()[0]
    conn.close()
    assert count == 2
    assert "declining" in rows


def test_breakout_requires_statistical_significance(temp_db):
    import analyzer

    # +100% endpoint move that is within the keyword's historical swing
    _seed_keyword(
        temp_db, "wobbler", "beauty",
        [30, 15, 60, 15, 60, 15, 60, 15, 60, 15, 60, 15, 60],
    )
    # Same magnitude move on a previously flat keyword
    _seed_keyword(temp_db, "spiker", "beauty", [30] * 12 + [60])

    breakouts = analyzer.detect_breakouts()
    names = [b["keyword"] for b in breakouts]
    assert "spiker" in names
    assert "wobbler" not in names


def test_seasonal_breakout_capped_at_info(temp_db):
    import analyzer

    this_year = [90, 90, 60, 40, 30, 30, 30, 30, 30, 30, 30, 30, 30]
    filler = [25] * 37
    last_year = [90, 90, 60, 40, 30, 30]
    # oldest first for seeding
    _seed_keyword(temp_db, "sunscreen", "beauty",
                  list(reversed(this_year + filler + last_year)))

    breakouts = analyzer.detect_breakouts()
    assert len(breakouts) == 1
    b = breakouts[0]
    assert b["is_seasonal"] is True
    assert b["severity"] == "info"  # +200% would otherwise be critical
