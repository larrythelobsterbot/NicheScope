#!/usr/bin/env python3
"""
Manual refresh: run all collectors immediately, one by one.

Usage:
  python3 scripts/refresh_now.py              # all collectors (~3.5 hrs)
  python3 scripts/refresh_now.py --fast        # quick ones only (~45 min)
  python3 scripts/refresh_now.py --only google_trends,tiktok
  python3 scripts/refresh_now.py --skip etsy,alibaba

Run from the project root (/opt/nichescope on VPS).
"""

import argparse
import gc
import logging
import os
import sqlite3
import sys
import time

# Ensure collectors/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "collectors"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [REFRESH] %(levelname)s: %(message)s",
)
logger = logging.getLogger("refresh")


# ── Collector imports (lazy, so missing API keys don't crash the whole script)

def run_google_trends():
    from google_trends import collect_trends
    count = collect_trends()
    return f"{count} data points collected"


def run_tiktok():
    from tiktok_trends import collect_tiktok_trends
    count = collect_tiktok_trends()
    return f"{count} keywords processed"


def run_alibaba():
    from alibaba_collector import collect_alibaba_suppliers
    count = collect_alibaba_suppliers()
    return f"{count} new suppliers discovered"


def run_competitor_traffic():
    from similarweb import collect_competitor_traffic
    count = collect_competitor_traffic()
    return f"{count} domains updated"


def run_keepa():
    if not os.getenv("KEEPA_API_KEY"):
        return "SKIPPED (no KEEPA_API_KEY)"
    from keepa_collector import collect_products
    count = collect_products()
    return f"{count} products updated"


def run_discovery():
    from discovery import run_discovery as _run_discovery
    count = _run_discovery()
    return f"{count} new pending keywords"


def run_reddit():
    from reddit_discovery import discover_from_reddit
    count = discover_from_reddit()
    return f"{count} new pending keywords"


def run_etsy():
    from etsy_discovery import discover_from_etsy
    count = discover_from_etsy()
    return f"{count} new pending keywords"


def run_amazon_bestsellers():
    from amazon_bestsellers import collect_amazon_bestsellers
    count = collect_amazon_bestsellers()
    return f"{count} new pending keywords"


def run_analysis():
    from analyzer import run_analysis as _run_analysis
    results = _run_analysis()
    breakouts = results.get("breakouts", [])
    return f"{len(breakouts)} breakout signals"


# ── Registry: order matters (cheapest/fastest API calls first)

COLLECTORS = {
    "google_trends":      ("Google Trends",            run_google_trends),
    "tiktok":             ("TikTok Trends",            run_tiktok),
    "discovery":          ("Discovery (category)",     run_discovery),
    "reddit":             ("Reddit Discovery",         run_reddit),
    "etsy":               ("Etsy Discovery",           run_etsy),
    "amazon_bestsellers": ("Amazon Best Sellers",      run_amazon_bestsellers),
    "alibaba":            ("Alibaba Suppliers",        run_alibaba),
    "competitor_traffic":  ("Competitor Traffic",       run_competitor_traffic),
    "keepa":              ("Keepa (Amazon)",           run_keepa),
    "analysis":           ("Niche Analysis",           run_analysis),
}

# Slow collectors skipped in --fast mode (Etsy ~82min, SimilarWeb ~50min, Alibaba ~31min)
SLOW_COLLECTORS = {"etsy", "alibaba", "competitor_traffic", "keepa"}


def main():
    parser = argparse.ArgumentParser(description="Run NicheScope collectors now")
    parser.add_argument(
        "--only",
        help="Comma-separated list of collectors to run (default: all)",
        default=None,
    )
    parser.add_argument(
        "--skip",
        help="Comma-separated list of collectors to skip",
        default=None,
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Quick refresh: skip slow collectors (Etsy, Alibaba, SimilarWeb, Keepa). ~45 min instead of ~3.5 hrs.",
    )
    args = parser.parse_args()

    # Determine which collectors to run
    if args.only:
        selected = [c.strip() for c in args.only.split(",")]
        to_run = {k: v for k, v in COLLECTORS.items() if k in selected}
    elif args.fast:
        to_run = {k: v for k, v in COLLECTORS.items() if k not in SLOW_COLLECTORS}
        logger.info("⚡ Fast mode: skipping Etsy, Alibaba, SimilarWeb, Keepa")
    elif args.skip:
        skipped = [c.strip() for c in args.skip.split(",")]
        to_run = {k: v for k, v in COLLECTORS.items() if k not in skipped}
    else:
        to_run = COLLECTORS

    total = len(to_run)
    logger.info(f"Starting manual refresh: {total} collectors")
    logger.info(f"Collectors: {', '.join(to_run.keys())}")
    print()

    results = {}
    for i, (key, (name, func)) in enumerate(to_run.items(), 1):
        print(f"[{i}/{total}] {name}...", flush=True)
        start = time.time()
        try:
            result = func()
            elapsed = time.time() - start
            results[key] = ("OK", result, elapsed)
            print(f"  ✓ {result} ({elapsed:.1f}s)")
        except Exception as e:
            elapsed = time.time() - start
            results[key] = ("FAIL", str(e)[:200], elapsed)
            print(f"  ✗ FAILED: {e} ({elapsed:.1f}s)")

        # Force-close any lingering SQLite connections between collectors
        gc.collect()
        time.sleep(1)
        print()

    # Summary
    print("=" * 60)
    print("REFRESH SUMMARY")
    print("=" * 60)
    ok = sum(1 for s, _, _ in results.values() if s == "OK")
    fail = sum(1 for s, _, _ in results.values() if s == "FAIL")
    total_time = sum(t for _, _, t in results.values())

    for key, (status, msg, elapsed) in results.items():
        icon = "✓" if status == "OK" else "✗"
        name = COLLECTORS[key][0] if key in COLLECTORS else key
        print(f"  {icon} {name}: {msg} ({elapsed:.1f}s)")

    print()
    print(f"Done: {ok} succeeded, {fail} failed, {total_time:.1f}s total")


if __name__ == "__main__":
    main()
