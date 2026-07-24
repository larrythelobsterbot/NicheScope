#!/usr/bin/env python3
"""Audit or deactivate historical active keywords matched by junk rules.

Dry-run is the default. Applying changes creates a SQLite backup first and
refuses a batch larger than --max-changes unless the operator raises the cap.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTORS = ROOT / "collectors"
sys.path.insert(0, str(COLLECTORS))

from config import DB_PATH  # noqa: E402
from keyword_filter import is_junk  # noqa: E402
from pending_triage import sweep_active_junk  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--all-history", action="store_true", help="scan the entire active watchlist")
    scope.add_argument("--days", type=int, default=14, help="recent-day window (default: 14)")
    parser.add_argument("--apply", action="store_true", help="deactivate matches after creating a backup")
    parser.add_argument("--max-changes", type=int, default=250, help="refuse larger apply batches")
    parser.add_argument("--sample-size", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    days = None if args.all_history else max(args.days, 1)
    database_path = Path(DB_PATH).expanduser().resolve()

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    if days is None:
        rows = connection.execute(
            "SELECT id, keyword, category FROM keywords WHERE is_active = 1 ORDER BY id"
        ).fetchall()
        scope = "all history"
    else:
        rows = connection.execute(
            "SELECT id, keyword, category FROM keywords WHERE is_active = 1 "
            "AND added_at >= datetime('now', ?) ORDER BY id",
            (f"-{days} days",),
        ).fetchall()
        scope = f"last {days} days"
    connection.close()

    matches: list[tuple[sqlite3.Row, str]] = []
    for row in rows:
        junk, reason = is_junk(row["keyword"])
        if junk:
            matches.append((row, reason or "unknown"))

    print(f"Scope: {scope}")
    print(f"Scanned: {len(rows):,} active keywords")
    print(f"Matched: {len(matches):,}")
    if matches:
        print("Reasons:")
        for reason, count in Counter(reason for _, reason in matches).most_common():
            print(f"  {count:>6,}  {reason}")
        print("Sample:")
        for row, reason in matches[: max(args.sample_size, 0)]:
            print(f"  [{row['id']}] {row['keyword']} ({row['category']}) — {reason}")

    if not args.apply:
        print("Dry run only; no rows changed.")
        return 0
    if not matches:
        print("No changes needed.")
        return 0
    if len(matches) > args.max_changes:
        print(
            f"Refusing to deactivate {len(matches):,} rows; "
            f"raise --max-changes above that count after reviewing the dry run.",
            file=sys.stderr,
        )
        return 2

    backup_dir = database_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"{database_path.stem}-before-junk-sweep-{stamp}.db"
    source = sqlite3.connect(database_path)
    backup = sqlite3.connect(backup_path)
    source.backup(backup)
    backup.close()
    source.close()

    changed = sweep_active_junk(days=days, apply=True)
    print(f"Backup: {backup_path}")
    print(f"Deactivated: {changed:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
