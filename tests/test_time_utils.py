from datetime import UTC, datetime


def test_utc_now_returns_naive_utc_for_sqlite_compatibility():
    from time_utils import utc_now

    before = datetime.now(UTC).replace(tzinfo=None)
    actual = utc_now()
    after = datetime.now(UTC).replace(tzinfo=None)

    assert actual.tzinfo is None
    assert before <= actual <= after
