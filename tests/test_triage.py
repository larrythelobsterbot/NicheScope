"""Tests for pending-keyword auto-triage, junk-filter extension, and
discovery parent rebalancing."""
import sqlite3

import pytest


def _db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _seed_active(db_path, category, count):
    conn = _db(db_path)
    for i in range(count):
        conn.execute(
            "INSERT INTO keywords (keyword, category, is_active) VALUES (?, ?, 1)",
            (f"{category} filler {i}", category),
        )
    conn.commit()
    conn.close()


def _add_pending(db_path, keyword, category, relevance, source="google_related",
                 age_days=1, parent="parent kw"):
    conn = _db(db_path)
    conn.execute(
        """INSERT INTO pending_keywords
           (keyword, suggested_category, source, parent_keyword,
            relevance_score, status, discovered_at)
           VALUES (?, ?, ?, ?, ?, 'pending', datetime('now', ?))""",
        (keyword, category, source, parent, relevance, f"-{age_days} days"),
    )
    conn.commit()
    conn.close()


def _status(db_path, keyword):
    conn = _db(db_path)
    row = conn.execute(
        "SELECT status FROM pending_keywords WHERE keyword = ?", (keyword,)
    ).fetchone()
    conn.close()
    return row["status"] if row else None


def _is_tracked(db_path, keyword):
    conn = _db(db_path)
    row = conn.execute(
        "SELECT 1 FROM keywords WHERE keyword = ? AND is_active = 1", (keyword,)
    ).fetchone()
    conn.close()
    return row is not None


# ---------- triage ----------

def test_triage_rejects_junk_low_relevance_and_stale(temp_db):
    from pending_triage import triage_pending

    _add_pending(temp_db, "where to watch demon hunter", "home", 0.8)
    _add_pending(temp_db, "barely relevant thing", "home", 0.1)
    _add_pending(temp_db, "old mediocre keyword", "home", 0.45, age_days=45)
    _add_pending(temp_db, "middle band keyword", "home", 0.45, age_days=5)

    success, actioned, err = triage_pending()
    assert success and err is None
    assert actioned == 3

    assert _status(temp_db, "where to watch demon hunter") == "auto_rejected"
    assert _status(temp_db, "barely relevant thing") == "auto_rejected"
    assert _status(temp_db, "old mediocre keyword") == "auto_rejected"
    assert _status(temp_db, "middle band keyword") == "pending"


def test_triage_approves_strong_keyword_into_keywords_table(temp_db):
    from pending_triage import triage_pending

    _seed_active(temp_db, "home", 5)
    _seed_active(temp_db, "jewelry", 5)
    _seed_active(temp_db, "travel", 5)
    _add_pending(temp_db, "ceramic pour over coffee set", "home", 0.75)

    triage_pending()

    assert _status(temp_db, "ceramic pour over coffee set") == "auto_approved"
    assert _is_tracked(temp_db, "ceramic pour over coffee set")

    conn = _db(temp_db)
    stats = conn.execute(
        "SELECT total_approved FROM discovery_stats WHERE source = 'google_related'"
    ).fetchone()
    conn.close()
    assert stats["total_approved"] == 1


def test_triage_blocks_auto_approval_for_dominant_category(temp_db):
    from pending_triage import triage_pending

    # beauty holds 90% of active keywords — far over the 40% share cap
    _seed_active(temp_db, "beauty", 18)
    _seed_active(temp_db, "home", 2)
    _add_pending(temp_db, "yet another serum", "beauty", 0.9)
    _add_pending(temp_db, "walnut bookshelf riser", "home", 0.9)

    triage_pending()

    # strong beauty keyword stays for human review; home one is approved
    assert _status(temp_db, "yet another serum") == "pending"
    assert _status(temp_db, "walnut bookshelf riser") == "auto_approved"


def test_triage_approves_aged_strong_keyword_before_stale_sweep(temp_db):
    from pending_triage import triage_pending

    _seed_active(temp_db, "home", 5)
    _seed_active(temp_db, "jewelry", 5)
    _seed_active(temp_db, "travel", 5)
    _add_pending(temp_db, "linen duvet cover", "home", 0.8, age_days=45)

    triage_pending()
    assert _status(temp_db, "linen duvet cover") == "auto_approved"


def test_triage_respects_per_category_cap(temp_db):
    import pending_triage
    from config import TRIAGE

    _seed_active(temp_db, "home", 5)
    _seed_active(temp_db, "jewelry", 5)
    _seed_active(temp_db, "travel", 5)
    cap = TRIAGE["max_auto_approvals_per_category"]
    for i in range(cap + 3):
        _add_pending(temp_db, f"good home keyword {i}", "home", 0.9)

    pending_triage.triage_pending()

    conn = _db(temp_db)
    approved = conn.execute(
        "SELECT COUNT(*) FROM pending_keywords WHERE status = 'auto_approved'"
    ).fetchone()[0]
    still_pending = conn.execute(
        "SELECT COUNT(*) FROM pending_keywords WHERE status = 'pending'"
    ).fetchone()[0]
    conn.close()
    assert approved == cap
    assert still_pending == 3


def test_triage_empty_queue_returns_skip_reason(temp_db):
    from pending_triage import triage_pending

    success, actioned, err = triage_pending()
    assert success and actioned == 0
    assert err == "queue empty"  # so the stall guard ignores it


# ---------- junk filter extension ----------

def test_non_latin_with_product_indicator_passes():
    from keyword_filter import is_junk

    # mixed-script product searches outside beauty
    assert is_junk("ohora ネイル strips")[0] is False
    assert is_junk("珪藻土 bath mat organizer")[0] is False
    assert is_junk("титан ring hypoallergenic")[0] is False
    # beauty waiver still works
    assert is_junk("mediheal 面膜 serum")[0] is False
    # pure non-Latin with no product signal still blocked
    assert is_junk("今日のニュース速報")[0] is True


# ---------- discovery parent rebalancing ----------

def test_discovery_parents_capped_and_interleaved(temp_db):
    from discovery import _select_discovery_parents
    from config import DISCOVERY

    cap = DISCOVERY["parents_per_category"]
    keywords = {
        "beauty": [f"beauty kw {i}" for i in range(cap * 4)],
        "home": ["home kw 1", "home kw 2"],
        "jewelry": ["jewelry kw 1"],
    }

    conn = _db(temp_db)
    parents = _select_discovery_parents(conn, keywords, set())
    conn.close()

    by_cat = {}
    for cat, _ in parents:
        by_cat[cat] = by_cat.get(cat, 0) + 1
    assert by_cat["beauty"] == cap  # capped, not 4x cap
    assert by_cat["home"] == 2
    assert by_cat["jewelry"] == 1

    # Interleaved: the first three entries cover all three categories
    first_cats = {cat for cat, _ in parents[:3]}
    assert first_cats == {"beauty", "home", "jewelry"}


def test_discovery_parents_prefer_rising_keywords(temp_db):
    from discovery import _select_discovery_parents
    from migrate_004_keyword_metrics import migrate
    migrate(temp_db)

    conn = _db(temp_db)
    cur = conn.execute(
        "INSERT INTO keywords (keyword, category, is_active) VALUES ('slow kw', 'home', 1)"
    )
    slow_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO keywords (keyword, category, is_active) VALUES ('fast kw', 'home', 1)"
    )
    fast_id = cur.lastrowid
    conn.execute(
        "INSERT INTO keyword_metrics (keyword_id, velocity_4w) VALUES (?, 5)", (slow_id,)
    )
    conn.execute(
        "INSERT INTO keyword_metrics (keyword_id, velocity_4w) VALUES (?, 150)", (fast_id,)
    )
    conn.commit()

    parents = _select_discovery_parents(
        conn, {"home": ["slow kw", "fast kw"]}, set()
    )
    conn.close()
    assert parents[0] == ("home", "fast kw")


def test_bulk_import_trash_wave_patterns():
    """July 2026 bulk import bypassed the filter; these patterns now catch it."""
    from keyword_filter import is_junk

    for junk in ["saiyaara showtimes", "wuthering heights streaming",
                 "our unwritten seoul ep 10 eng sub bilibili",
                 "mcx gold silver prices", "gold and silver price today india",
                 "2026 winter olympics medals", "pension kyc", "maps",
                 "saja boys png", "your idol latin translation"]:
        assert is_junk(junk)[0] is True, junk
    for keep in ["olympic barbell set", "14k gold necklace",
                 "streaming microphone for podcasting", "epsom salt bath",
                 "world map wall art", "silver jewelry cleaner"]:
        assert is_junk(keep)[0] is False, keep


def test_sweep_active_junk_recent_only(temp_db):
    from pending_triage import sweep_active_junk

    conn = _db(temp_db)
    # recent junk (bulk-imported yesterday) -> swept
    conn.execute("INSERT INTO keywords (keyword, category, is_active, added_at) "
                 "VALUES ('saiyaara showtimes', 'beauty', 1, datetime('now','-1 day'))")
    # recent legit -> kept
    conn.execute("INSERT INTO keywords (keyword, category, is_active, added_at) "
                 "VALUES ('14k gold necklace', 'jewelry', 1, datetime('now','-1 day'))")
    # OLD junk (predates window) -> untouched by this sweep
    conn.execute("INSERT INTO keywords (keyword, category, is_active, added_at) "
                 "VALUES ('trump news', 'beauty', 1, datetime('now','-90 days'))")
    conn.commit(); conn.close()

    swept = sweep_active_junk(days=14)
    assert swept == 1
    assert _is_tracked(temp_db, "saiyaara showtimes") is False
    assert _is_tracked(temp_db, "14k gold necklace") is True
    assert _is_tracked(temp_db, "trump news") is True  # outside window


def test_bulk_import_approved_past_share_cap_but_junk_filtered(temp_db):
    """Owner bulk imports bypass the share cap and relevance bar, but junk
    is still rejected — this is the fix for the July 2026 import that
    bypassed the filter entirely."""
    from pending_triage import triage_pending

    _seed_active(temp_db, "beauty", 18)  # beauty way over the 40% share cap
    _seed_active(temp_db, "home", 2)
    _add_pending(temp_db, "anua pdrn 100 serum", "beauty", 0.7,
                 source="bulk_import", parent="serums")
    _add_pending(temp_db, "saiyaara showtimes", "beauty", 0.7,
                 source="bulk_import")

    triage_pending()

    # non-junk import approved despite dominant category, subcategory carried
    assert _status(temp_db, "anua pdrn 100 serum") == "auto_approved"
    conn = _db(temp_db)
    row = conn.execute(
        "SELECT category, subcategory, is_active FROM keywords WHERE keyword='anua pdrn 100 serum'"
    ).fetchone()
    conn.close()
    assert row["is_active"] == 1 and row["category"] == "beauty"
    assert row["subcategory"] == "serums"
    # junk import rejected
    assert _status(temp_db, "saiyaara showtimes") == "auto_rejected"
    assert _is_tracked(temp_db, "saiyaara showtimes") is False
