"""Niche score components report whether they used real or fallback data."""
import json
import sqlite3

import pytest


@pytest.fixture(autouse=True)
def _apply_migrations(temp_db):
    from migrate_002_content_trends import migrate as m2
    from migrate_004_keyword_metrics import migrate as m4
    from migrate_005_score_provenance import migrate as m5
    m2(temp_db)
    m4(temp_db)
    m5(temp_db)


def _db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def test_margin_real_vs_fallback(temp_db):
    from analyzer import _calc_margin_score

    conn = _db(temp_db)
    cur = conn.cursor()

    # No products / suppliers -> fallback
    score, src = _calc_margin_score(cur, "beauty")
    assert src == "fallback"
    assert score == 75  # the hardcoded beauty default

    # Real retail price + structured supplier cost -> real
    cur.execute("INSERT INTO products (asin, category) VALUES ('B0X', 'beauty')")
    cur.execute(
        """INSERT INTO product_history (product_id, date, price)
           VALUES (1, datetime('now'), 30.0)"""
    )
    cur.execute(
        """INSERT INTO suppliers (name, product_focus, price_low, price_high)
           VALUES ('Acme', 'beauty supplies', 5.0, 10.0)"""
    )
    conn.commit()
    score, src = _calc_margin_score(cur, "beauty")
    conn.close()
    assert src == "real"
    # margin = (30 - 7.5)/30 = 75% -> (75-10)*100/60 clamped to 100
    assert score == 100


def test_competition_no_data_is_fallback_not_perfect_score(temp_db):
    from analyzer import _calc_competition_score

    conn = _db(temp_db)
    score, src = _calc_competition_score(conn.cursor(), "beauty")
    assert src == "fallback"
    assert score < 100  # absence of competitors is not evidence of none

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO competitors (name, domain, category) VALUES ('X', 'x.com', 'beauty')"
    )
    conn.commit()
    score, src = _calc_competition_score(cur, "beauty")
    conn.close()
    assert src == "real"


def test_niche_scores_persist_provenance(temp_db):
    import analyzer

    conn = _db(temp_db)
    cur = conn.execute(
        "INSERT INTO keywords (keyword, category, is_active) VALUES ('kw', 'beauty', 1)"
    )
    kid = cur.lastrowid
    for i in range(13):
        conn.execute(
            """INSERT INTO trend_data (keyword_id, date, interest_score)
               VALUES (?, date('now', ?), ?)""",
            (kid, f"-{(12 - i) * 7} days", 30 + i),
        )
    conn.commit()
    conn.close()

    analyzer.compute_all_metrics()
    scores = analyzer.calculate_niche_scores()

    assert scores["beauty"]["provenance"]["trend"] == "real"
    assert scores["beauty"]["provenance"]["margin"] == "fallback"

    conn = _db(temp_db)
    row = conn.execute(
        "SELECT provenance FROM niche_scores WHERE category = 'beauty'"
    ).fetchone()
    conn.close()
    stored = json.loads(row["provenance"])
    assert stored["margin"] == "fallback"
    assert stored["trend"] == "real"
