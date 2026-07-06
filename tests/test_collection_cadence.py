"""Lifecycle-weighted collection: which keywords are due, and in what order."""
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


def _kw(db_path, keyword, category, lifecycle=None, interest=0,
        last_collected_days=None):
    """Insert a keyword, optional metrics row, and an optional last-collected
    trend_data point (collected_at = N days ago)."""
    conn = _db(db_path)
    kid = conn.execute(
        "INSERT INTO keywords (keyword, category, is_active) VALUES (?, ?, 1)",
        (keyword, category),
    ).lastrowid
    if lifecycle is not None or interest:
        conn.execute(
            """INSERT INTO keyword_metrics (keyword_id, lifecycle, current_interest)
               VALUES (?, ?, ?)""",
            (kid, lifecycle, interest),
        )
    if last_collected_days is not None:
        conn.execute(
            """INSERT INTO trend_data (keyword_id, date, interest_score, collected_at)
               VALUES (?, date('now'), ?, datetime('now', ?))""",
            (kid, interest, f"-{last_collected_days} days"),
        )
    conn.commit()
    conn.close()
    return kid


def _due_keywords(temp_db, monkeypatch):
    import config
    monkeypatch.setattr(config, "DB_PATH", temp_db)
    return config.get_keywords_due_for_collection()


def test_rising_due_daily_stable_not_due_after_recent_collection(temp_db, monkeypatch):
    # accelerating, collected yesterday -> due (daily cadence)
    _kw(temp_db, "rising kw", "home", "accelerating", 80, last_collected_days=1)
    # stable, collected 2 days ago -> NOT due (weekly cadence)
    _kw(temp_db, "stable kw", "home", "stable", 40, last_collected_days=2)
    # stable, collected 10 days ago -> due
    _kw(temp_db, "stale stable kw", "home", "stable", 30, last_collected_days=10)
    # declining, collected 10 days ago -> NOT due (monthly cadence)
    _kw(temp_db, "declining kw", "home", "declining", 5, last_collected_days=10)

    due = {kw for kw, _ in _due_keywords(temp_db, monkeypatch)}
    assert "rising kw" in due
    assert "stale stable kw" in due
    assert "stable kw" not in due
    assert "declining kw" not in due


def test_new_keyword_with_no_metrics_is_due(temp_db, monkeypatch):
    _kw(temp_db, "brand new kw", "home")  # no metrics, no trend_data
    due = {kw for kw, _ in _due_keywords(temp_db, monkeypatch)}
    assert "brand new kw" in due


def test_categories_block_together_and_urgent_first(temp_db, monkeypatch):
    """Batches must never mix categories (Google normalizes a batch to its max
    keyword — mixing magnitudes quantizes niche series: the July 2026
    corruption). Order: urgent categories first, category-contiguous, stable."""
    _kw(temp_db, "wellness stable", "wellness", "stable", 50, last_collected_days=60)
    _kw(temp_db, "travel rising", "travel", "emerging", 70, last_collected_days=60)
    _kw(temp_db, "travel stable", "travel", "stable", 90, last_collected_days=60)
    _kw(temp_db, "wellness stable 2", "wellness", "stable", 40, last_collected_days=60)

    due = _due_keywords(temp_db, monkeypatch)
    cats = [cat for _, cat in due]
    # travel has a rising keyword -> travel block first, then wellness block
    assert cats == ["travel", "travel", "wellness", "wellness"]
    # stable alphabetical order within a category (consistent normalization)
    travel_kws = [kw for kw, cat in due if cat == "travel"]
    assert travel_kws == sorted(travel_kws)


def test_due_list_never_interleaves_categories(temp_db, monkeypatch):
    for i in range(7):
        _kw(temp_db, f"home kw {i}", "home", "stable", 30, last_collected_days=60)
    for i in range(3):
        _kw(temp_db, f"pets kw {i}", "pets", "stable", 30, last_collected_days=60)

    cats = [cat for _, cat in _due_keywords(temp_db, monkeypatch)]
    # each category appears as one contiguous block
    seen, blocks = set(), 0
    prev = None
    for c in cats:
        if c != prev:
            blocks += 1
            assert c not in seen, f"category {c} appears in two separate blocks"
            seen.add(c)
            prev = c
    assert blocks == 2


def test_returns_keyword_category_pairs(temp_db, monkeypatch):
    _kw(temp_db, "travel kw", "travel", "emerging", 60, last_collected_days=5)
    due = _due_keywords(temp_db, monkeypatch)
    assert ("travel kw", "travel") in due
