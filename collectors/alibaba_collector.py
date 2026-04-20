"""
Supplier data collector. Multiple sources, tiered approach:

TIER 1: Alibaba Affiliate/Open API (if registered)
TIER 2: Web scraping fallback (careful with rate limits)
TIER 3: Manual entry through dashboard admin UI
"""

import re
import sqlite3
import time
import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from config import DB_PATH, ALIBABA_APP_KEY, ALIBABA_APP_SECRET, get_active_keywords
from rate_limiter import ALIBABA_SCRAPE, RateLimitExceeded

logger = logging.getLogger(__name__)

ALIBABA_SEARCH_URL = "https://www.alibaba.com/trade/search"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_price(price_str: str) -> tuple:
    """Extract (price_low, price_high) floats from freeform price strings.
    Handles: '$2.50-$5.00/unit', 'US $1.20 - 3.50', '¥15-30', etc.
    Returns (None, None) if unparseable.
    """
    if not price_str:
        return (None, None)
    # Remove currency symbols and unit suffixes
    cleaned = re.sub(r'[^\d.\-\s]', '', price_str.replace(',', ''))
    # Find all numbers
    numbers = re.findall(r'(\d+\.?\d*)', cleaned)
    if len(numbers) >= 2:
        return (float(numbers[0]), float(numbers[1]))
    elif len(numbers) == 1:
        val = float(numbers[0])
        return (val, val)
    return (None, None)


def collect_alibaba_suppliers():
    """Search Alibaba for suppliers matching tracked keywords.

    Returns (success, items_written, error | None). Never raises.
    """
    try:
        keywords = get_active_keywords()
        db = get_db()
        total_collected = 0

        for category, kw_list in keywords.items():
            # Only search a few keywords per category to stay within rate limits
            for keyword in kw_list[:3]:
                logger.info(f"Searching Alibaba for: {keyword} ({category})")

                try:
                    ALIBABA_SCRAPE.wait_if_needed()
                except RateLimitExceeded as e:
                    logger.warning(f"Stopping Alibaba collection: {e}")
                    db.close()
                    return (True, total_collected, str(e))

                if ALIBABA_APP_KEY:
                    results = search_alibaba_api(keyword)
                else:
                    results = search_alibaba_scrape(keyword)

                for supplier in results:
                    try:
                        price_low, price_high = normalize_price(supplier.get("price", ""))
                        db.execute(
                            """INSERT OR IGNORE INTO suppliers
                               (name, region, product_focus, price_range, price_low, price_high, moq,
                                lead_time, quality_score, certifications, contact_url, notes)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                supplier.get("name", "Unknown"),
                                supplier.get("region", ""),
                                supplier.get("product", ""),
                                supplier.get("price", ""),
                                price_low,
                                price_high,
                                supplier.get("moq", ""),
                                supplier.get("lead_time", ""),
                                supplier.get("quality", 5),
                                supplier.get("certs", "[]"),
                                supplier.get("url", ""),
                                f"Auto-discovered for: {keyword} ({category})",
                            ),
                        )
                        if db.total_changes:
                            total_collected += 1
                    except Exception as e:
                        logger.warning(f"Failed to store supplier: {e}")

                ALIBABA_SCRAPE.record_request()
                db.commit()
                # Rate limit: 30+ seconds between keyword searches
                time.sleep(35)

        db.close()
        logger.info(f"Alibaba collection complete. {total_collected} new suppliers discovered.")
        return (True, total_collected, None)
    except Exception as e:
        logger.error(f"Alibaba top-level error: {e}", exc_info=True)
        return (False, 0, str(e))


def search_alibaba_api(keyword: str) -> list:
    """Use Alibaba Open API to search suppliers. Returns list of dicts."""
    if not ALIBABA_APP_KEY or not ALIBABA_APP_SECRET:
        return []

    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(
                "https://api.alibaba.com/param2/1/portals.open/api.findProducts",
                params={
                    "app_key": ALIBABA_APP_KEY,
                    "keywords": keyword,
                    "page_size": 10,
                    "language": "en",
                },
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("products", []):
                results.append({
                    "name": item.get("supplierName", ""),
                    "region": item.get("supplierLocation", ""),
                    "product": item.get("productTitle", ""),
                    "price": item.get("priceRange", ""),
                    "moq": item.get("minOrder", ""),
                    "quality": min(10, max(1, int(item.get("transactionLevel", 5)))),
                    "certs": "[]",
                    "url": item.get("productUrl", ""),
                })
            return results

    except Exception as e:
        logger.error(f"Alibaba API search failed: {e}")
        return []


def parse_search_html(html: str, keyword: str) -> list:
    """Parse Alibaba search HTML into a list of supplier dicts.

    NOTE: Selectors below are known-stale as of 2026-04-20. Alibaba bot-blocks
    direct unauthenticated fetches from the collector IP (returns a captcha /
    punish page instead of real results), so we cannot currently capture a
    valid response to re-derive selectors. Selector fix is deferred to a
    follow-up track; this function is kept as the single parsing entry-point
    so tests and refactors can target it once a real fixture is available.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Parse product cards from search results (selectors known-stale; see docstring)
    cards = soup.select(".organic-list .list-no-v2-outter .J-offer-wrapper")
    if not cards:
        cards = soup.select("[class*='offer']")

    for card in cards[:10]:
        try:
            name_el = card.select_one("[class*='company']")
            title_el = card.select_one("[class*='title']") or card.select_one("h2")
            price_el = card.select_one("[class*='price']")
            moq_el = card.select_one("[class*='moq']") or card.select_one("[class*='min-order']")
            location_el = card.select_one("[class*='location']")

            results.append({
                "name": name_el.get_text(strip=True) if name_el else "Unknown Supplier",
                "region": location_el.get_text(strip=True) if location_el else "",
                "product": title_el.get_text(strip=True)[:100] if title_el else keyword,
                "price": price_el.get_text(strip=True) if price_el else "",
                "moq": moq_el.get_text(strip=True) if moq_el else "",
                "quality": 5,
                "certs": "[]",
                "url": "",
            })
        except Exception as e:
            logger.debug(f"Failed to parse card: {e}")
            continue

    if not results:
        logger.warning(
            f"Alibaba parser found 0 cards for '{keyword}'. "
            "DOM may have drifted or IP is bot-blocked; "
            "re-capture tests/fixtures/alibaba_search_sample.html from a clean environment."
        )
    return results


def search_alibaba_scrape(keyword: str) -> list:
    """Fallback: scrape Alibaba search results. Use carefully."""
    import random

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(
                ALIBABA_SEARCH_URL,
                params={"SearchText": keyword},
                headers=headers,
            )

            if response.status_code != 200:
                logger.warning(f"Alibaba returned {response.status_code} for '{keyword}'")
                return []

            results = parse_search_html(response.text, keyword)
            logger.info(f"Scraped {len(results)} suppliers for '{keyword}'")
            return results

    except Exception as e:
        logger.error(f"Alibaba scrape failed for '{keyword}': {e}")
        return []


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if "--test" in sys.argv:
        logger.info("Running Alibaba collector test...")
        results = search_alibaba_scrape("nail stickers")
        for r in results[:3]:
            print(f"  {r['name']}: {r['product'][:50]} - {r['price']}")
        print(f"Found {len(results)} suppliers.")
    else:
        collect_alibaba_suppliers()
