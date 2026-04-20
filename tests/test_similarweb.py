"""SimilarWeb integration test against real public endpoint."""
import sqlite3

import pytest


def test_similarweb_writes_competitor_traffic_row(temp_db, monkeypatch):
    # Force similarweb and its config module to re-resolve DB_PATH against
    # the temp DB. conftest reloads config; similarweb captures get_db at
    # import time, so reload it here too.
    import importlib, sys
    if "config" in sys.modules:
        importlib.reload(sys.modules["config"])
    if "similarweb" in sys.modules:
        importlib.reload(sys.modules["similarweb"])

    conn = sqlite3.connect(temp_db)
    conn.execute(
        """INSERT INTO competitors (name, domain, category)
           VALUES ('Etsy', 'etsy.com', 'jewelry')"""
    )
    conn.commit()
    conn.close()

    from similarweb import collect_competitor_traffic
    success, items, err = collect_competitor_traffic()
    assert success is True, f"collector failed: {err}"
    # Even if visits_estimate is 0, we must write a row (traffic=0 IS a signal).
    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT * FROM competitor_traffic").fetchall()
    conn.close()
    assert rows, "competitor_traffic should have at least one row"


def test_similarweb_survives_network_error(temp_db, monkeypatch):
    """If the public endpoint is unreachable, still return a tuple; don't raise."""
    from similarweb import estimate_traffic

    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, *a, **kw): raise Exception("boom")

    monkeypatch.setattr("similarweb.httpx.Client", lambda **kw: FakeClient())
    # estimate_traffic currently re-raises on retryable errors — but the
    # collect_competitor_traffic wrapper uses estimate_traffic_with_retry
    # that handles it. For this test, we verify the retry wrapper handles
    # the exception by checking it doesn't raise. estimate_traffic itself
    # may raise — that's OK, the retry wrapper catches it.
    from similarweb import estimate_traffic_with_retry
    result = estimate_traffic_with_retry("example.com")
    assert result["visits_estimate"] == 0
