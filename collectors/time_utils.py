"""UTC timestamp helpers that preserve NicheScope's naive SQLite format."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return current UTC as a naive datetime for existing SQLite text fields."""
    return datetime.now(UTC).replace(tzinfo=None)
