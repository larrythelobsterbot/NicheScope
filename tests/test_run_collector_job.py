"""run_collector_job must record real success + row-delta per run."""
import sqlite3

import pytest


@pytest.fixture(autouse=True)
def _apply_migration_002(temp_db):
    from migrate_002_content_trends import migrate
    migrate(temp_db)


def test_wraps_tuple_return(temp_db, monkeypatch):
    import scheduler
    monkeypatch.setattr(scheduler, "DB_PATH", temp_db)

    def fake_collector():
        return (True, 42, None)

    result = scheduler.run_collector_job("fake_test", fake_collector)
    assert result == (True, 42, None)

    conn = sqlite3.connect(temp_db)
    row = conn.execute(
        "SELECT last_status, items_collected FROM collector_health "
        "WHERE collector_name = 'fake_test'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_records_failure_on_exception(temp_db, monkeypatch):
    import scheduler
    monkeypatch.setattr(scheduler, "DB_PATH", temp_db)

    def broken_collector():
        raise RuntimeError("boom")

    result = scheduler.run_collector_job("broken_test", broken_collector)
    assert result[0] is False
    assert result[1] == 0
    assert "boom" in (result[2] or "")


def test_normalizes_int_return_to_tuple(temp_db, monkeypatch):
    """Legacy collectors that still return an int count should still work."""
    import scheduler
    monkeypatch.setattr(scheduler, "DB_PATH", temp_db)

    def legacy_collector():
        return 7  # legacy signature

    result = scheduler.run_collector_job("legacy_test", legacy_collector)
    assert result == (True, 7, None)
