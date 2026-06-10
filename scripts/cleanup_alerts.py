#!/usr/bin/env python3
"""
One-time cleanup for the alerts table.

The analysis pipeline used to re-insert an alert for the same breakout every
time it ran (several times a day), with no expiry — leaving tens of thousands
of duplicate rows. This script:

  1. Deletes all but the most recent alert per (type, subject), where subject
     is the keyword (breakouts) or ASIN (price/stock alerts).
  2. Auto-acknowledges surviving alerts older than 30 days.

Default is a dry run that only reports counts. Pass --apply to execute.

Usage:
    python scripts/cleanup_alerts.py            # dry run
    python scripts/cleanup_alerts.py --apply    # delete + acknowledge
"""

import os
import sqlite3
import sys

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "nichescope.db")
)

EXPIRY_DAYS = 30

# Most recent alert per (type, subject) survives. Alerts whose data has no
# keyword/asin (e.g. malformed rows) fall back to grouping by message.
DUPLICATE_IDS_SQL = """
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY type,
                       COALESCE(
                           json_extract(data, '$.keyword'),
                           json_extract(data, '$.asin'),
                           json_extract(data, '$.collector'),
                           message
                       )
                   ORDER BY sent_at DESC, id DESC
               ) AS rn
        FROM alerts
    ) WHERE rn > 1
"""


def main():
    apply = "--apply" in sys.argv

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) AS c FROM alerts").fetchone()["c"]
    dupes = conn.execute(
        f"SELECT COUNT(*) AS c FROM ({DUPLICATE_IDS_SQL})"
    ).fetchone()["c"]
    stale = conn.execute(
        f"""SELECT COUNT(*) AS c FROM alerts
            WHERE acknowledged = 0
              AND sent_at < datetime('now', '-{EXPIRY_DAYS} days')
              AND id NOT IN ({DUPLICATE_IDS_SQL})"""
    ).fetchone()["c"]

    print(f"Database: {DB_PATH}")
    print(f"Total alerts:                {total:>8,}")
    print(f"Duplicates to delete:        {dupes:>8,}")
    print(f"Survivors after delete:      {total - dupes:>8,}")
    print(f"Stale survivors to ack:      {stale:>8,} (older than {EXPIRY_DAYS} days)")

    if not apply:
        print("\nDry run — nothing changed. Re-run with --apply to execute.")
        conn.close()
        return

    conn.execute(f"DELETE FROM alerts WHERE id IN ({DUPLICATE_IDS_SQL})")
    conn.execute(
        f"""UPDATE alerts SET acknowledged = 1
            WHERE acknowledged = 0
              AND sent_at < datetime('now', '-{EXPIRY_DAYS} days')"""
    )
    conn.commit()

    remaining = conn.execute("SELECT COUNT(*) AS c FROM alerts").fetchone()["c"]
    unread = conn.execute(
        "SELECT COUNT(*) AS c FROM alerts WHERE acknowledged = 0"
    ).fetchone()["c"]
    conn.execute("VACUUM")
    conn.close()

    print(f"\nDone. {remaining:,} alerts remain ({unread:,} unread).")


if __name__ == "__main__":
    main()
