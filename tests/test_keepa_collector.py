"""Keepa collector must return a tuple and warn loudly on empty ASIN list."""
import logging
import sqlite3

import pytest

from conftest import require_env


def test_empty_asins_returns_success_zero(temp_db, caplog, monkeypatch):
    caplog.set_level(logging.WARNING)
    import keepa_collector
    # Force past the "no API key" short-circuit so we exercise the
    # empty-ASINs warning path. Monkeypatch get_tracked_asins to avoid
    # hitting the real config and to guarantee an empty result.
    monkeypatch.setattr(keepa_collector, "KEEPA_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(keepa_collector, "get_tracked_asins", lambda: {})

    success, items, err = keepa_collector.collect_products()
    assert success is True
    assert items == 0
    assert any("ASIN" in rec.message or "seed_watchlist" in rec.message
               for rec in caplog.records)


def test_keepa_writes_products_when_configured(temp_db):
    require_env("KEEPA_API_KEY")
    conn = sqlite3.connect(temp_db)
    conn.execute(
        """INSERT INTO products (asin, title, category, is_active)
           VALUES ('B08N5WRWNW', 'placeholder', 'beauty', 1)"""
    )
    conn.commit()
    conn.close()

    from keepa_collector import collect_products
    success, items, err = collect_products()
    assert success is True, f"err: {err}"
    assert items >= 1
