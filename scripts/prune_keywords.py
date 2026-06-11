#!/usr/bin/env python3
"""
Prune dead keywords to reclaim Google Trends collection budget.

With ~11k active keywords and a 1,400 req/day Google Trends limit, each
keyword is only refreshed every ~8 days. Most of that budget is spent on
keywords nobody searches for anymore.

"Dead" is deliberately conservative:
  - tracked for at least 90 days (newcomers get time to develop), AND
  - peak interest over the last 84 days is below 5 (out of 100), AND
  - has at least 8 data points (we actually measured it, not just missed it)

Keywords are DEACTIVATED (is_active = 0), never deleted: trend history is
kept, and if discovery or a manual add surfaces the keyword again, the
existing upsert paths flip is_active back to 1 automatically.

Default is a dry run. Pass --apply to deactivate.

Usage:
    python scripts/prune_keywords.py            # report what would be pruned
    python scripts/prune_keywords.py --apply    # deactivate dead keywords
    python scripts/prune_keywords.py --max-peak 3 --apply   # stricter
"""

import argparse
import os
import sqlite3

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "nichescope.db")
)

DEAD_KEYWORDS_SQL = """
    SELECT k.id, k.keyword, k.category,
           MAX(td.interest_score) AS peak_recent,
           COUNT(td.id) AS recent_points
    FROM keywords k
    JOIN trend_data td ON td.keyword_id = k.id
        AND td.date >= date('now', '-84 days')
    WHERE k.is_active = 1
      -- tracked long enough to judge
      AND (SELECT MIN(date) FROM trend_data WHERE keyword_id = k.id)
              <= date('now', '-90 days')
    GROUP BY k.id
    HAVING MAX(td.interest_score) < :max_peak
       AND COUNT(td.id) >= 8
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="deactivate (default: dry run)")
    parser.add_argument("--max-peak", type=int, default=5,
                        help="peak interest threshold over last 84 days (default 5)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    dead = conn.execute(DEAD_KEYWORDS_SQL, {"max_peak": args.max_peak}).fetchall()
    total_active = conn.execute(
        "SELECT COUNT(*) FROM keywords WHERE is_active = 1"
    ).fetchone()[0]

    by_category = {}
    for row in dead:
        by_category.setdefault(row["category"], []).append(row)

    print(f"Database: {DB_PATH}")
    print(f"Active keywords:        {total_active:>7,}")
    print(f"Dead (peak <{args.max_peak} for 12w): {len(dead):>7,}")
    print(f"Would remain active:    {total_active - len(dead):>7,}")
    print()
    print("By category:")
    for cat, rows in sorted(by_category.items(), key=lambda x: -len(x[1])):
        sample = ", ".join(f"'{r['keyword'][:30]}'" for r in rows[:2])
        print(f"  {cat:20} {len(rows):>6,}   e.g. {sample}")

    if not args.apply:
        print("\nDry run — nothing changed. Re-run with --apply to deactivate.")
        conn.close()
        return

    conn.executemany(
        "UPDATE keywords SET is_active = 0 WHERE id = ?",
        [(r["id"],) for r in dead],
    )
    conn.commit()
    remaining = conn.execute(
        "SELECT COUNT(*) FROM keywords WHERE is_active = 1"
    ).fetchone()[0]
    conn.close()

    refresh_days = remaining / 1400
    print(f"\nDone. {remaining:,} keywords remain active "
          f"(~{refresh_days:.1f}-day Google Trends refresh cycle, was "
          f"~{total_active / 1400:.1f}).")


if __name__ == "__main__":
    main()
