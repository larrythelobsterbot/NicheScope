"""
NicheScope Discovery Mode
==========================
Finds trending product keywords across e-commerce categories
without requiring them to be on the watchlist first.

Sources:
1. Google Trends category-level rising topics
2. Google Trends related queries from existing keywords
3. Amazon Movers & Shakers page scraping (placeholder)

Results go into pending_keywords table for user approval.
"""

from pytrends.request import TrendReq
import sqlite3
import time
import logging
from config import DB_PATH, get_active_keywords
from rate_limiter import GOOGLE_TRENDS, RateLimitExceeded
from discovery_feedback import get_source_weights, should_skip_source, get_productive_parents

logger = logging.getLogger(__name__)

# Google Trends category IDs relevant to e-commerce
DISCOVERY_CATEGORIES = {
    18: "Shopping",
    44: "Beauty & Fitness",
    11: "Home & Garden",
    71: "Food & Drink",
    7: "Finance",
    5: "Computers & Electronics",
    68: "Travel",
    66: "Pets & Animals",
    70: "Sports",
    276: "Jewelry & Accessories",
    983: "Gift Giving",
    69: "Online Communities",
}

# Amazon Movers & Shakers category URLs (for future use)
AMAZON_MOVERS = {
    "beauty": "https://www.amazon.com/gp/movers-and-shakers/beauty/",
    "jewelry": "https://www.amazon.com/gp/movers-and-shakers/fashion/3885461/",
    "home": "https://www.amazon.com/gp/movers-and-shakers/home-garden/",
    "electronics": "https://www.amazon.com/gp/movers-and-shakers/electronics/",
    "pet_supplies": "https://www.amazon.com/gp/movers-and-shakers/pet-supplies/",
    "sports": "https://www.amazon.com/gp/movers-and-shakers/sporting-goods/",
    "toys": "https://www.amazon.com/gp/movers-and-shakers/toys-and-games/",
    "baby": "https://www.amazon.com/gp/movers-and-shakers/baby-products/",
    "kitchen": "https://www.amazon.com/gp/movers-and-shakers/kitchen/",
    "office": "https://www.amazon.com/gp/movers-and-shakers/office-products/",
    "automotive": "https://www.amazon.com/gp/movers-and-shakers/automotive/",
    "garden": "https://www.amazon.com/gp/movers-and-shakers/lawn-garden/",
}


def discover_from_google_categories():
    """
    Query Google Trends for rising topics in shopping-related categories.
    This catches trends you would never think to search for.
    """
    # Check if this source should be deprioritized
    if should_skip_source("google_category"):
        logger.info("Google category discovery deprioritized by feedback loop. Skipping.")
        return 0

    conn = sqlite3.connect(DB_PATH, timeout=30)
    existing = set(
        row[0].lower() for row in
        conn.execute("SELECT keyword FROM keywords WHERE is_active = 1").fetchall()
    )
    already_pending = set(
        row[0].lower() for row in
        conn.execute("SELECT keyword FROM pending_keywords WHERE status = 'pending'").fetchall()
    )

    pytrends = TrendReq(hl='en-US', tz=480)  # HKT timezone offset
    discovered = 0

    for cat_id, cat_name in DISCOVERY_CATEGORIES.items():
        try:
            GOOGLE_TRENDS.wait_if_needed()

            # Get trending topics in this category
            pytrends.build_payload(
                kw_list=[""],  # empty keyword to get category-level data
                cat=cat_id,
                timeframe="today 3-m",
                geo=""
            )

            related = pytrends.related_topics()
            GOOGLE_TRENDS.record_request()

            if not related or "" not in related:
                continue

            rising = related[""].get("rising")
            if rising is None or rising.empty:
                continue

            for _, row in rising.iterrows():
                topic = row.get("topic_title", "").strip().lower()
                value = row.get("value", 0)

                # Skip if already tracked or pending
                if not topic or topic in existing or topic in already_pending:
                    continue

                # Skip single-character or very generic terms
                if len(topic) < 3:
                    continue

                # Map Google category to our category names
                suggested_cat = map_google_cat_to_niche(cat_id)

                conn.execute("""
                    INSERT OR IGNORE INTO pending_keywords
                    (keyword, suggested_category, source, parent_keyword, relevance_score)
                    VALUES (?, ?, 'google_category', ?, ?)
                """, (topic, suggested_cat, cat_name, min(value / 1000, 1.0)))

                discovered += 1
                already_pending.add(topic)

        except RateLimitExceeded:
            logger.warning("Rate limit hit during discovery. Stopping.")
            break
        except Exception as e:
            logger.error(f"Error discovering in category {cat_name}: {e}")
            time.sleep(5)

    conn.commit()
    conn.close()
    return discovered


def discover_from_related_queries():
    """
    For each tracked keyword, check its rising related queries.
    Surface any that we are not already tracking.
    """
    if should_skip_source("google_related"):
        logger.info("Google related queries deprioritized by feedback loop. Skipping.")
        return 0

    # Get productive parents to prioritize
    productive = get_productive_parents("google_related")
    productive_keywords = {p["parent"].lower() for p in productive}

    conn = sqlite3.connect(DB_PATH, timeout=30)
    keywords = get_active_keywords()
    existing = set(
        row[0].lower() for row in
        conn.execute("SELECT keyword FROM keywords WHERE is_active = 1").fetchall()
    )
    already_pending = set(
        row[0].lower() for row in
        conn.execute("SELECT keyword FROM pending_keywords WHERE status = 'pending'").fetchall()
    )

    pytrends = TrendReq(hl='en-US', tz=480)
    discovered = 0

    for category, kw_list in keywords.items():
        # Sort: productive keywords first
        sorted_kws = sorted(kw_list, key=lambda k: k.lower() in productive_keywords, reverse=True)
        for keyword in sorted_kws:
            try:
                GOOGLE_TRENDS.wait_if_needed()
                pytrends.build_payload([keyword], timeframe="today 3-m")
                related = pytrends.related_queries()
                GOOGLE_TRENDS.record_request()

                if not related or keyword not in related:
                    continue

                rising = related[keyword].get("rising")
                if rising is None or rising.empty:
                    continue

                for _, row in rising.iterrows():
                    query = row.get("query", "").strip().lower()
                    value = row.get("value", 0)

                    if not query or query in existing or query in already_pending:
                        continue

                    conn.execute("""
                        INSERT OR IGNORE INTO pending_keywords
                        (keyword, suggested_category, source, parent_keyword, relevance_score)
                        VALUES (?, ?, 'google_related', ?, ?)
                    """, (query, category, keyword, min(value / 1000, 1.0)))

                    discovered += 1
                    already_pending.add(query)

            except RateLimitExceeded:
                logger.warning("Rate limit hit. Stopping discovery.")
                conn.commit()
                conn.close()
                return discovered
            except Exception as e:
                logger.error(f"Error on related queries for {keyword}: {e}")
                time.sleep(5)

    conn.commit()
    conn.close()
    return discovered


def discover_from_amazon_movers():
    """
    Scrape Amazon Movers & Shakers pages for products with
    big sales rank jumps. Extract product keywords.

    Note: Amazon actively blocks scrapers. Use carefully with
    rotating user agents and long delays. If this breaks,
    the Google-based discovery still works fine.
    """
    # TODO: Implement with requests + BeautifulSoup
    # Extract product titles from movers & shakers pages
    # Parse titles into keyword candidates
    # Filter against existing keywords
    # Insert into pending_keywords with source='amazon_movers'
    return 0


def map_google_cat_to_niche(cat_id):
    """Map Google Trends category IDs to NicheScope categories."""
    mapping = {
        18: "general",
        44: "beauty",
        11: "home",
        71: "food",
        7: "tech_accessories",
        5: "tech_accessories",
        68: "travel",
        66: "pets",
        70: "fitness",
        276: "jewelry",
        983: "wedding_events",
        69: "general",
    }
    return mapping.get(cat_id, "general")


def run_discovery():
    """Main entry point for the discovery collector."""
    logger.info("Running NicheScope Discovery Mode...")

    d1 = discover_from_google_categories()
    logger.info(f"  Category scan: {d1} new keywords discovered")

    d2 = discover_from_related_queries()
    logger.info(f"  Related queries: {d2} new keywords discovered")

    # d3 = discover_from_amazon_movers()
    # logger.info(f"  Amazon movers: {d3} new keywords discovered")

    d4 = 0
    try:
        from reddit_discovery import discover_from_reddit
        d4 = discover_from_reddit()
        logger.info(f"  Reddit discovery: {d4} new keywords discovered")
    except Exception as e:
        logger.error(f"  Reddit discovery failed: {e}")

    d5 = 0
    try:
        from etsy_discovery import discover_from_etsy
        d5 = discover_from_etsy()
        logger.info(f"  Etsy discovery: {d5} new keywords discovered")
    except Exception as e:
        logger.error(f"  Etsy discovery failed: {e}")

    total = d1 + d2 + d4 + d5
    logger.info(f"  Total: {total} new pending keywords awaiting approval")
    return total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_discovery()
