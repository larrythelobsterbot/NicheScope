#!/usr/bin/env python3
"""
NicheScope Bulk Keyword Importer
================================
Imports keywords from a CSV file into the NicheScope SQLite database.

Usage:
    python import_keywords.py keywords.csv
    python import_keywords.py keywords.csv --db ../data/nichescope.db
    python import_keywords.py keywords.csv --dry-run
    python import_keywords.py keywords.csv --category-only beauty,jewelry

CSV Format:
    category,keyword,subcategory,priority
    beauty,nail stickers,nail art,high

The script will:
1. Create any new categories that don't exist yet
2. Insert keywords (skip duplicates)
3. Report what was added vs skipped
"""

import csv
import sqlite3
import sys
import os
from datetime import datetime

DEFAULT_DB_PATH = "../data/nichescope.db"

# Auto-assigned color palette (matches frontend)
CATEGORY_PALETTE = [
    "#FF6B8A",  # pink
    "#A78BFA",  # purple
    "#34D399",  # green
    "#FBBF24",  # amber
    "#60A5FA",  # blue
    "#FB923C",  # orange
    "#F472B6",  # hot pink
    "#2DD4BF",  # teal
    "#C084FC",  # violet
    "#4ADE80",  # lime
    "#E879F9",  # fuchsia
    "#38BDF8",  # sky
    "#A3E635",  # yellow-green
    "#F97316",  # deep orange
    "#818CF8",  # indigo
]


def get_db_path():
    """Find the database file, checking common locations."""
    candidates = [
        DEFAULT_DB_PATH,
        "./data/nichescope.db",
        "../nichescope/data/nichescope.db",
        os.path.expanduser("~/nichescope/data/nichescope.db"),
        "/opt/nichescope/data/nichescope.db",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def ensure_tables(conn):
    """Make sure required tables exist (in case DB was just created)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color_override TEXT,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            subcategory TEXT,
            priority TEXT DEFAULT 'medium',
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    """)
    conn.commit()


def import_csv(csv_path, db_path, dry_run=False, category_filter=None):
    """Import keywords from CSV into the NicheScope database."""
    
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)
    
    conn = sqlite3.connect(db_path)
    ensure_tables(conn)
    
    # Track existing state
    existing_keywords = set(
        row[0] for row in conn.execute("SELECT keyword FROM keywords").fetchall()
    )
    existing_categories = set(
        row[0] for row in conn.execute("SELECT name FROM categories").fetchall()
    )
    
    # Parse CSV
    added_keywords = 0
    skipped_keywords = 0
    new_categories = set()
    category_counts = {}
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    # Filter by category if specified
    if category_filter:
        filter_set = set(c.strip().lower() for c in category_filter.split(","))
        rows = [r for r in rows if r["category"].strip().lower() in filter_set]
    
    print(f"\nNicheScope Bulk Import")
    print(f"{'=' * 50}")
    print(f"CSV file: {csv_path}")
    print(f"Database: {db_path}")
    print(f"Total rows in CSV: {len(rows)}")
    print(f"Existing keywords in DB: {len(existing_keywords)}")
    print(f"Existing categories in DB: {len(existing_categories)}")
    if dry_run:
        print(f"MODE: DRY RUN (no changes will be made)")
    print(f"{'=' * 50}\n")
    
    for row in rows:
        category = row["category"].strip()
        keyword = row["keyword"].strip()
        subcategory = row.get("subcategory", "").strip()
        priority = row.get("priority", "medium").strip()
        
        # Track category counts for summary
        category_counts.setdefault(category, {"new": 0, "skipped": 0})
        
        # Create category if new
        if category not in existing_categories and category not in new_categories:
            new_categories.add(category)
            cat_index = len(existing_categories) + len(new_categories) - 1
            color = CATEGORY_PALETTE[cat_index % len(CATEGORY_PALETTE)]
            
            if not dry_run:
                conn.execute(
                    "INSERT OR IGNORE INTO categories (name, color_override, sort_order) VALUES (?, ?, ?)",
                    (category, color, cat_index)
                )
            print(f"  + New category: {category} (color: {color})")
        
        # Insert keyword
        if keyword in existing_keywords:
            skipped_keywords += 1
            category_counts[category]["skipped"] += 1
        else:
            added_keywords += 1
            existing_keywords.add(keyword)
            category_counts[category]["new"] += 1
            
            if not dry_run:
                try:
                    conn.execute(
                        "INSERT INTO keywords (keyword, category, subcategory, priority) VALUES (?, ?, ?, ?)",
                        (keyword, category, subcategory or None, priority)
                    )
                except sqlite3.IntegrityError:
                    skipped_keywords += 1
                    added_keywords -= 1
                    category_counts[category]["new"] -= 1
                    category_counts[category]["skipped"] += 1
    
    if not dry_run:
        conn.commit()
    
    # Print summary
    print(f"\nResults by Category:")
    print(f"{'-' * 50}")
    print(f"{'Category':<25} {'Added':>8} {'Skipped':>8} {'Total':>8}")
    print(f"{'-' * 50}")
    
    for cat in sorted(category_counts.keys()):
        counts = category_counts[cat]
        total = counts["new"] + counts["skipped"]
        marker = " [NEW]" if cat in new_categories else ""
        print(f"{cat + marker:<25} {counts['new']:>8} {counts['skipped']:>8} {total:>8}")
    
    print(f"{'-' * 50}")
    print(f"{'TOTAL':<25} {added_keywords:>8} {skipped_keywords:>8} {added_keywords + skipped_keywords:>8}")
    print()
    
    if new_categories:
        print(f"New categories created: {', '.join(sorted(new_categories))}")
    
    print(f"\nKeywords added: {added_keywords}")
    print(f"Keywords skipped (already exist): {skipped_keywords}")
    
    if dry_run:
        print(f"\nThis was a DRY RUN. No changes were made.")
        print(f"Run without --dry-run to apply changes.")
    else:
        total_kw = conn.execute("SELECT COUNT(*) FROM keywords WHERE is_active = 1").fetchone()[0]
        total_cat = conn.execute("SELECT COUNT(*) FROM categories WHERE is_active = 1").fetchone()[0]
        print(f"\nDatabase now has {total_kw} active keywords across {total_cat} categories.")
        print(f"The next collector run will automatically pick up all new keywords.")
    
    conn.close()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="NicheScope Bulk Keyword Importer")
    parser.add_argument("csv_file", help="Path to CSV file with keywords")
    parser.add_argument("--db", default=None, help="Path to NicheScope SQLite database")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing to DB")
    parser.add_argument("--category-only", default=None, help="Only import specific categories (comma-separated)")
    
    args = parser.parse_args()
    
    # Find database
    db_path = args.db
    if not db_path:
        db_path = get_db_path()
        if not db_path:
            print("Error: Could not find nichescope.db")
            print("Specify the path with: --db /path/to/nichescope.db")
            sys.exit(1)
    
    import_csv(args.csv_file, db_path, dry_run=args.dry_run, category_filter=args.category_only)


if __name__ == "__main__":
    main()
