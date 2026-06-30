#!/usr/bin/env python3
"""
Prune dead keywords to reclaim Google Trends collection budget.

Thin CLI over collectors/pruner.py — the same logic the scheduler runs weekly,
so the definition of "dead" can't drift between the two.

"Dead" (see config.PRUNE) is deliberately conservative:
  - tracked for at least 90 days (newcomers get time to develop), AND
  - peak interest over the last 84 days is below 5 (out of 100), AND
  - has at least 8 data points (we actually measured it, not just missed it)

Keywords are DEACTIVATED (is_active = 0), never deleted: trend history is kept,
and if discovery or a manual add surfaces the keyword again the existing upsert
paths flip is_active back to 1 automatically.

Default is a dry run. Pass --apply to deactivate.

Usage:
    python scripts/prune_keywords.py            # report what would be pruned
    python scripts/prune_keywords.py --apply    # deactivate dead keywords
    python scripts/prune_keywords.py --max-peak 3 --apply   # stricter
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "collectors"))

from pruner import find_dead_keywords, prune_dead_keywords  # noqa: E402

DB_PATH = os.environ.get(
    "DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "nichescope.db")
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="deactivate (default: dry run)")
    parser.add_argument("--max-peak", type=int, default=None,
                        help="override peak-interest threshold (default from config.PRUNE)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    dead = find_dead_keywords(conn, max_peak=args.max_peak)
    total_active = conn.execute("SELECT COUNT(*) FROM keywords WHERE is_active = 1").fetchone()[0]
    conn.close()

    by_category = {}
    for row in dead:
        by_category.setdefault(row["category"], []).append(row["keyword"])

    print(f"Database: {DB_PATH}")
    print(f"Active keywords:        {total_active:>7,}")
    print(f"Dead (peak below cutoff): {len(dead):>7,}")
    print(f"Would remain active:    {total_active - len(dead):>7,}")
    print()
    print("By category:")
    for cat, kws in sorted(by_category.items(), key=lambda x: -len(x[1])):
        sample = ", ".join(f"'{k[:30]}'" for k in kws[:2])
        print(f"  {cat:20} {len(kws):>6,}   e.g. {sample}")

    if not args.apply:
        print("\nDry run — nothing changed. Re-run with --apply to deactivate.")
        return

    success, count, err = prune_dead_keywords(apply=True, max_peak=args.max_peak)
    remaining = total_active - count
    print(f"\nDone. Deactivated {count:,}; {remaining:,} keywords remain active "
          f"(~{remaining / 1400:.1f}-day Google Trends refresh cycle, was "
          f"~{total_active / 1400:.1f}).")
    if not success:
        print(f"ERROR: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
