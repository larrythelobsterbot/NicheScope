#!/usr/bin/env python3
"""
cleanup-junk-keywords.py — NicheScope keyword audit & cleanup tool
===================================================================
Identifies active keywords that match junk patterns, outputs a CSV
report, and optionally deletes confirmed junk from the database.

Usage
-----
  # Dry-run (default): just produce the CSV + summary
  python3 cleanup-junk-keywords.py

  # Delete only HIGH confidence junk (with confirmation prompt)
  python3 cleanup-junk-keywords.py --delete

  # Delete HIGH + MEDIUM confidence junk (separate prompts)
  python3 cleanup-junk-keywords.py --delete-all

  # Explicit dry-run (same as no flags)
  python3 cleanup-junk-keywords.py --dry-run

Confidence levels
-----------------
  HIGH   — junk pattern matched AND (interest == 0 OR no trend data at all)
  MEDIUM — junk pattern matched BUT keyword has some recorded interest > 0
"""

import argparse
import csv
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date

# ---------------------------------------------------------------------------
# Path setup — allow running from scripts/ directory
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_COLLECTORS_DIR = os.path.join(_SCRIPT_DIR, "..", "collectors")
sys.path.insert(0, os.path.abspath(_COLLECTORS_DIR))

from keyword_filter import is_junk  # noqa: E402

# ---------------------------------------------------------------------------
# DB path — fall back to hardcoded location if config import fails
# ---------------------------------------------------------------------------
try:
    from config import DB_PATH  # noqa: E402
except ImportError:
    DB_PATH = os.path.abspath(
        os.path.join(_SCRIPT_DIR, "..", "data", "nichescope.db")
    )

# ---------------------------------------------------------------------------
# CSV output path
# ---------------------------------------------------------------------------
_TODAY = date.today().strftime("%Y%m%d")
CSV_PATH = f"/tmp/nichescope-junk-{_TODAY}.csv"

# ---------------------------------------------------------------------------
# Column headers
# ---------------------------------------------------------------------------
CSV_COLUMNS = ["id", "keyword", "category", "interest", "flags", "confidence", "recommendation"]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def fetch_keywords_with_interest(conn: sqlite3.Connection) -> list[dict]:
    """
    Return all active keywords joined with their latest interest score.
    If a keyword has no trend_data rows its interest is reported as None.
    """
    rows = conn.execute("""
        SELECT
            k.id,
            k.keyword,
            k.category,
            MAX(td.interest_score) AS max_interest
        FROM keywords k
        LEFT JOIN trend_data td ON td.keyword_id = k.id
        WHERE k.is_active = 1
        GROUP BY k.id, k.keyword, k.category
        ORDER BY k.category, k.keyword
    """).fetchall()

    result = []
    for row in rows:
        result.append({
            "id": row[0],
            "keyword": row[1],
            "category": row[2] or "unknown",
            "interest": row[3],  # None if no trend data
        })
    return result


def delete_keywords(conn: sqlite3.Connection, ids: list[int]) -> int:
    """
    Delete keywords (and their trend_data rows) by id list.
    Returns number of keywords deleted.
    """
    if not ids:
        return 0

    placeholders = ",".join("?" * len(ids))

    # Delete trend_data first (in case there's no ON DELETE CASCADE)
    conn.execute(
        f"DELETE FROM trend_data WHERE keyword_id IN ({placeholders})", ids
    )
    conn.execute(
        f"DELETE FROM keywords WHERE id IN ({placeholders})", ids
    )
    conn.commit()
    return len(ids)


# ---------------------------------------------------------------------------
# Core audit logic
# ---------------------------------------------------------------------------

def audit_keywords(keywords: list[dict]) -> list[dict]:
    """
    Run is_junk() against every keyword and build an annotated record
    including confidence level and recommendation.
    """
    results = []
    for kw in keywords:
        junk, reason = is_junk(kw["keyword"])
        if not junk:
            continue

        interest = kw["interest"]  # None = never had trend data; 0 = recorded zero

        # Confidence assignment
        if interest is None or interest == 0:
            confidence = "HIGH"
            recommendation = "delete"
        else:
            confidence = "MEDIUM"
            recommendation = "review"

        results.append({
            "id": kw["id"],
            "keyword": kw["keyword"],
            "category": kw["category"],
            "interest": interest if interest is not None else "",
            "flags": reason,
            "confidence": confidence,
            "recommendation": recommendation,
        })

    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def write_csv(records: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(records)


def print_summary(records: list[dict]) -> None:
    """Print a human-readable table grouped by category."""
    if not records:
        print("\nNo junk keywords detected.")
        return

    # Aggregate
    by_cat: dict[str, dict[str, list]] = defaultdict(lambda: {"HIGH": [], "MEDIUM": []})
    for r in records:
        by_cat[r["category"]][r["confidence"]].append(r["keyword"])

    total_high = sum(len(v["HIGH"]) for v in by_cat.values())
    total_med = sum(len(v["MEDIUM"]) for v in by_cat.values())

    print()
    print("=" * 72)
    print(f"  NicheScope Junk Keyword Audit — {date.today().isoformat()}")
    print("=" * 72)
    print(f"  Total flagged : {len(records)}  "
          f"(HIGH: {total_high}, MEDIUM: {total_med})")
    print()
    print(f"  {'Category':<28}  {'HIGH':>6}  {'MEDIUM':>7}")
    print(f"  {'-'*28}  {'-'*6}  {'-'*7}")
    for cat in sorted(by_cat):
        h = len(by_cat[cat]["HIGH"])
        m = len(by_cat[cat]["MEDIUM"])
        print(f"  {cat:<28}  {h:>6}  {m:>7}")
    print(f"  {'TOTAL':<28}  {total_high:>6}  {total_med:>7}")
    print("=" * 72)
    print()


def confirm(prompt: str) -> bool:
    """Prompt for y/n confirmation. Returns True only on explicit 'y'."""
    try:
        answer = input(prompt + " [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit and optionally clean up junk keywords in NicheScope."
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Only produce the CSV + summary; do not delete anything (default behavior).",
    )
    parser.add_argument(
        "--delete", action="store_true", default=False,
        help="Delete HIGH confidence junk keywords after confirmation.",
    )
    parser.add_argument(
        "--delete-all", action="store_true", default=False,
        help="Delete HIGH and MEDIUM confidence junk keywords (separate confirmations).",
    )
    args = parser.parse_args()

    # Sanity: treat no flags the same as --dry-run
    if not args.delete and not args.delete_all:
        args.dry_run = True

    # ---------------------------------------------------------------------------
    print(f"Connecting to database: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH, timeout=30)

    print("Fetching active keywords...")
    keywords = fetch_keywords_with_interest(conn)
    print(f"  {len(keywords)} active keywords found.")

    print("Running junk filter...")
    junk_records = audit_keywords(keywords)
    print(f"  {len(junk_records)} junk keywords detected.")

    # Write CSV
    write_csv(junk_records, CSV_PATH)
    print(f"  CSV written to: {CSV_PATH}")

    # Print summary
    print_summary(junk_records)

    if args.dry_run:
        print("Dry-run mode: no changes made to the database.")
        conn.close()
        return

    # ---------------------------------------------------------------------------
    # Deletion logic
    # ---------------------------------------------------------------------------
    high_ids = [r["id"] for r in junk_records if r["confidence"] == "HIGH"]
    med_ids  = [r["id"] for r in junk_records if r["confidence"] == "MEDIUM"]

    if args.delete or args.delete_all:
        if high_ids:
            print(f"Deleting {len(high_ids)} HIGH confidence junk keywords...")
            if confirm(f"  Permanently delete {len(high_ids)} HIGH confidence records?"):
                deleted = delete_keywords(conn, high_ids)
                print(f"  Deleted {deleted} keywords (+ their trend_data rows).")
            else:
                print("  Skipped HIGH confidence deletion.")
        else:
            print("No HIGH confidence junk keywords to delete.")

    if args.delete_all and med_ids:
        print(f"\nDeleting {len(med_ids)} MEDIUM confidence junk keywords...")
        if confirm(f"  Permanently delete {len(med_ids)} MEDIUM confidence records?"):
            deleted = delete_keywords(conn, med_ids)
            print(f"  Deleted {deleted} keywords (+ their trend_data rows).")
        else:
            print("  Skipped MEDIUM confidence deletion.")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
