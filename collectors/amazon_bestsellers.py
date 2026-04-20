"""
Amazon Best Sellers Scraper
=============================
Scrapes Amazon's public best sellers pages by category and extracts product
titles. Adds them to pending_keywords as discovery candidates with source
'amazon_bestsellers'.

Why this matters:
- Best sellers = products people are ACTUALLY BUYING right now
- Cross-reference with Google Trends to find buy-intent vs search-intent gaps
- Free, no API key, just respectful HTTP scraping

Public pages used:
  - Top-level:    https://www.amazon.com/gp/bestsellers/{slug}/
  - Subcategory:  https://www.amazon.com/x/zgbs/{root}/{node_id}/

Rate limited via the existing rate_limiter to avoid getting blocked.
"""

import logging
import re
import sqlite3
import time
from datetime import datetime
from typing import List, Tuple

import httpx
from bs4 import BeautifulSoup

from config import DB_PATH
from rate_limiter import RateLimiter, RateLimitExceeded

logger = logging.getLogger(__name__)

# Conservative rate limiter — Amazon WILL block aggressive scraping
AMAZON_BS = RateLimiter(
    service_name="amazon_bestsellers",
    requests_per_minute=2,    # ~30 sec between requests
    daily_limit=200,          # Hard cap to avoid IP blocks
)

# Amazon best-seller targets.
#
# Two URL patterns are supported:
#   - Top-level categories: /gp/bestsellers/{slug}/
#   - Subcategories:        /x/zgbs/{root}/{node_id}/
#
# Each entry: (label, url_path, our_category)
#   - label:      human-readable name for logging + parent_keyword
#   - url_path:   URL path starting after https://www.amazon.com/
#   - our_category: maps into our internal category names
AMAZON_BESTSELLER_NODES: List[Tuple[str, str, str]] = [
    # ── Beauty (top + subcategories) ─────────────────────────
    ("beauty",            "gp/bestsellers/beauty",              "beauty"),
    ("luxury-beauty",     "gp/bestsellers/luxury-beauty",       "beauty"),
    ("skin-care",         "x/zgbs/beauty/11060451",             "beauty"),
    ("makeup",            "x/zgbs/beauty/11058281",             "beauty"),
    ("hair-care",         "x/zgbs/beauty/11057241",             "beauty"),
    ("fragrance",         "x/zgbs/beauty/11056591",             "beauty"),
    ("foot-hand-nail",    "x/zgbs/beauty/17242866011",          "beauty"),
    ("tools-accessories", "x/zgbs/beauty/11062741",             "beauty"),
    ("personal-care",     "x/zgbs/beauty/3777891",              "beauty"),
    ("shave-hair-removal","x/zgbs/beauty/3778591",              "beauty"),

    # ── Home ─────────────────────────────────────────────────
    ("home-garden",       "gp/bestsellers/home-garden",         "home"),
    ("kitchen",           "gp/bestsellers/kitchen",             "home"),

    # ── Fashion (gender breakdowns instead of shoes/jewelry) ─
    ("fashion",           "gp/bestsellers/fashion",             "fashion"),
    ("womens-fashion",    "x/zgbs/fashion/7147440011",          "fashion"),
    ("mens-fashion",      "x/zgbs/fashion/7147441011",          "fashion"),
    ("shoe-jewelry-watch","x/zgbs/fashion/7586146011",          "fashion"),
    ("luggage-travel",    "x/zgbs/fashion/9479199011",          "travel"),

    # ── Pets ─────────────────────────────────────────────────
    ("pet-supplies",      "gp/bestsellers/pet-supplies",        "pets"),

    # ── Baby & kids ──────────────────────────────────────────
    ("baby-products",     "gp/bestsellers/baby-products",       "baby_kids"),
    ("toys-and-games",    "gp/bestsellers/toys-and-games",      "baby_kids"),

    # ── Sports / fitness ─────────────────────────────────────
    ("sporting-goods",    "gp/bestsellers/sporting-goods",      "fitness_gear"),

    # ── Electronics / smart home ─────────────────────────────
    ("electronics",       "gp/bestsellers/electronics",         "smart_home"),

    # ── Gaming ───────────────────────────────────────────────
    ("videogames",        "gp/bestsellers/videogames",          "gaming_merch"),

    # ── Health / wellness ────────────────────────────────────
    ("hpc",               "gp/bestsellers/hpc",                 "wellness"),
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.6 Safari/605.1.15"
)

# Words to strip out of scraped product titles to get usable keywords
NOISE_WORDS = {
    "amazon", "the", "and", "for", "with", "from", "your", "you", "our",
    "this", "that", "all", "new", "set", "pack", "kit", "bundle", "size",
    "count", "pieces", "pcs", "ct", "oz", "fl", "ml", "lb", "lbs", "inch",
    "inches", "in", "of", "to", "by", "on", "at", "or", "are", "is",
}


def _open_conn():
    """Open SQLite connection in autocommit mode with WAL + busy_timeout."""
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    return conn


def fetch_bestsellers_page(url_path: str) -> List[dict]:
    """Fetch one Amazon best sellers page and parse out product titles + ranks.

    Args:
        url_path: Path after https://www.amazon.com/ (no leading slash).
                  Supports both "gp/bestsellers/beauty" and
                  "x/zgbs/beauty/11060451" formats.

    Returns a list of {title, rank, asin?} dicts.
    """
    url = f"https://www.amazon.com/{url_path}/"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        # httpx auto-decompresses gzip/br when no Accept-Encoding override is set
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            products: List[dict] = []

            # Each best-seller item has id like "p13n-asin-index-0" through 49
            items = soup.find_all("div", id=re.compile(r"^p13n-asin-index-\d+$"))

            for item in items[:50]:
                # Rank from the id
                m = re.search(r"p13n-asin-index-(\d+)", item.get("id", ""))
                rank = int(m.group(1)) + 1 if m else None

                # Title from the product image alt text (most reliable)
                img = item.find("img", alt=True)
                title = img.get("alt", "").strip() if img else None

                # ASIN from the product link
                asin = None
                link = item.find("a", href=re.compile(r"/dp/[A-Z0-9]{10}"))
                if link:
                    am = re.search(r"/dp/([A-Z0-9]{10})", link["href"])
                    if am:
                        asin = am.group(1)

                if title and len(title) >= 10:
                    products.append({
                        "title": title,
                        "rank": rank,
                        "asin": asin,
                    })

            return products

    except httpx.HTTPStatusError as e:
        if e.response.status_code in (503, 429):
            logger.warning(f"Amazon blocked us on {url_path} ({e.response.status_code}). Backing off.")
        else:
            logger.error(f"Amazon HTTP error on {url_path}: {e}")
        return []
    except Exception as e:
        logger.error(f"Amazon scrape failed for {url_path}: {e}")
        return []


def extract_keyword_from_title(title: str) -> str:
    """
    Reduce a long product title into a searchable keyword.

    Strategy: take the first 4-6 meaningful words, drop noise.
    Example:
      "Beauty of Joseon Relief Sun Rice + Probiotic Sunscreen 50ml SPF50+ PA++++"
      → "beauty of joseon relief sun"
    """
    # Lowercase, remove punctuation
    t = re.sub(r"[^\w\s]", " ", title.lower())
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()

    words = t.split()

    # Take meaningful words: skip pure numbers, units, noise words
    meaningful: List[str] = []
    for w in words:
        if w in NOISE_WORDS:
            # Allow noise words AFTER we have something meaningful, for natural flow
            if 1 <= len(meaningful) <= 4:
                meaningful.append(w)
            continue
        if w.isdigit():
            continue
        if re.match(r"^\d+\w*$", w):  # e.g. "50ml", "32oz"
            continue
        meaningful.append(w)
        if len(meaningful) >= 6:
            break

    # Trim trailing noise words
    while meaningful and meaningful[-1] in NOISE_WORDS:
        meaningful.pop()

    if len(meaningful) < 2:
        return ""

    return " ".join(meaningful[:6])


def collect_amazon_bestsellers() -> int:
    """
    Scrape Amazon best sellers across all configured categories and add
    new product keywords to pending_keywords.
    """
    # Read existing keywords once
    conn = _open_conn()
    existing = set(
        row[0].lower() for row in
        conn.execute("SELECT keyword FROM keywords WHERE is_active = 1").fetchall()
    )
    already_pending = set(
        row[0].lower() for row in
        conn.execute("SELECT keyword FROM pending_keywords WHERE status = 'pending'").fetchall()
    )
    conn.close()

    discovered = 0

    for label, url_path, our_category in AMAZON_BESTSELLER_NODES:
        try:
            AMAZON_BS.wait_if_needed()
        except RateLimitExceeded:
            logger.warning("Amazon best sellers rate limit reached. Stopping.")
            return discovered

        logger.info(f"Scraping Amazon best sellers: {label} → {our_category}")
        products = fetch_bestsellers_page(url_path)
        AMAZON_BS.record_request()

        if not products:
            logger.warning(f"No products parsed for {label}. Page layout may have changed.")
            time.sleep(5)
            continue

        # Open per-category connection
        cat_conn = _open_conn()
        cat_added = 0
        try:
            for product in products:
                keyword = extract_keyword_from_title(product["title"])
                if not keyword or len(keyword) < 4:
                    continue
                if keyword in existing or keyword in already_pending:
                    continue

                # Relevance score from rank: rank 1 = 1.0, rank 50 = 0.02
                rank = product.get("rank") or 25
                relevance = max(0.02, 1.0 - (rank - 1) / 50)

                try:
                    cat_conn.execute("""
                        INSERT OR IGNORE INTO pending_keywords
                        (keyword, suggested_category, source, parent_keyword, relevance_score)
                        VALUES (?, ?, 'amazon_bestsellers', ?, ?)
                    """, (keyword, our_category, label, relevance))
                    discovered += 1
                    cat_added += 1
                    already_pending.add(keyword)
                except Exception as e:
                    logger.debug(f"Failed to insert keyword '{keyword}': {e}")
        finally:
            cat_conn.close()

        logger.info(f"  → {cat_added} new keywords from {label}")
        time.sleep(5)  # Be respectful

    logger.info(f"Amazon best sellers complete. {discovered} new keywords found.")
    return discovered


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    collect_amazon_bestsellers()
