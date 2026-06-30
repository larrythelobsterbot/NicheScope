"""Dead-keyword pruning: conservative deactivation, reversible, callable."""
import sqlite3

import pytest


def _db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _seed(db_path, keyword, category, scores, first_age_days):
    """Insert a keyword with `scores` as weekly points within the recent
    84-day window (newest last), plus an anchor point `first_age_days` ago so
    the min-age check has history to look at."""
    conn = _db(db_path)
    kid = conn.execute(
        "INSERT INTO keywords (keyword, category, is_active) VALUES (?, ?, 1)",
        (keyword, category),
    ).lastrowid
    # Age anchor (only matters for the MIN(date) age check; old + low interest)
    if first_age_days > 84:
        conn.execute(
            """INSERT INTO trend_data (keyword_id, date, interest_score)
               VALUES (?, date('now', ?), 0)""",
            (kid, f"-{first_age_days} days"),
        )
    # Recent weekly points inside the window (oldest first)
    n = len(scores)
    for i, score in enumerate(scores):
        age = (n - 1 - i) * 7  # 0, 7, 14, ... days ago
        conn.execute(
            """INSERT INTO trend_data (keyword_id, date, interest_score)
               VALUES (?, date('now', ?), ?)""",
            (kid, f"-{age} days", score),
        )
    conn.commit()
    conn.close()
    return kid


def _active(db_path, keyword):
    conn = _db(db_path)
    row = conn.execute(
        "SELECT is_active FROM keywords WHERE keyword = ?", (keyword,)
    ).fetchone()
    conn.close()
    return row["is_active"]


def test_prune_deactivates_dead_keeps_others(temp_db, monkeypatch):
    import pruner
    monkeypatch.setattr(pruner, "DB_PATH", temp_db)

    # Dead: old, 12 weeks of near-zero interest, plenty of points
    _seed(temp_db, "dead nail thing", "beauty", [1, 2, 1, 0, 2, 1, 1, 0, 2, 1], 200)
    # Alive: old but clearly searched (peak 60)
    _seed(temp_db, "carry on luggage", "travel", [30, 40, 60, 50, 45, 55, 40, 50], 200)
    # Too new: low interest but only tracked 20 days — spared
    _seed(temp_db, "brand new gadget", "home", [1, 2, 1, 2, 1, 2, 1, 2], 20)
    # Too few points: low interest, old, but only 3 data points — spared
    _seed(temp_db, "barely measured", "pets", [1, 2, 1], 200)

    success, count, err = pruner.prune_dead_keywords(apply=True)
    assert success and err is None
    assert count == 1

    assert _active(temp_db, "dead nail thing") == 0
    assert _active(temp_db, "carry on luggage") == 1
    assert _active(temp_db, "brand new gadget") == 1
    assert _active(temp_db, "barely measured") == 1


def test_prune_dry_run_changes_nothing(temp_db, monkeypatch):
    import pruner
    monkeypatch.setattr(pruner, "DB_PATH", temp_db)

    _seed(temp_db, "dead thing", "beauty", [1, 1, 0, 2, 1, 1, 0, 1, 2, 1], 200)
    success, count, err = pruner.prune_dead_keywords(apply=False)
    assert success and count == 1
    assert err == "dry-run"  # so the stall guard ignores it
    assert _active(temp_db, "dead thing") == 1  # untouched


def test_prune_reactivation_via_upsert(temp_db, monkeypatch):
    """A pruned keyword re-approved through the normal upsert path comes back."""
    import pruner
    monkeypatch.setattr(pruner, "DB_PATH", temp_db)

    _seed(temp_db, "seasonal sleeper", "beauty", [1, 1, 0, 2, 1, 1, 0, 1, 2, 1], 200)
    pruner.prune_dead_keywords(apply=True)
    assert _active(temp_db, "seasonal sleeper") == 0

    conn = _db(temp_db)
    conn.execute(
        """INSERT INTO keywords (keyword, category, is_active) VALUES (?, ?, 1)
           ON CONFLICT(keyword) DO UPDATE SET is_active = 1""",
        ("seasonal sleeper", "beauty"),
    )
    conn.commit()
    conn.close()
    assert _active(temp_db, "seasonal sleeper") == 1
