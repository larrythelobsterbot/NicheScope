"""
NicheScope Etsy Discovery
===========================
Discovers trending product keywords from Etsy's search suggestions
and trending items. Uses public endpoints, no API key required.
"""

import sqlite3
import re
import time
import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from config import DB_PATH, get_active_keywords
from rate_limiter import RateLimiter, RateLimitExceeded

logger = logging.getLogger(__name__)

# Etsy rate limiter: very conservative since we're using public pages
ETSY = RateLimiter(
    service_name="etsy",
    requests_per_minute=2,
    daily_limit=200
)

# Seed search terms mapped to categories
ETSY_SEARCH_SEEDS = {
    "beauty": ["nail art", "lashes", "skincare", "cosmetics", "hair accessories"],
    "jewelry": ["handmade jewelry", "minimalist rings", "statement earrings", "charm bracelets"],
    "travel": ["travel accessories", "packing organizer", "luggage tags", "passport holder"],
    "home": ["home decor", "wall art", "candles", "kitchen gadgets", "organization"],
    "pets": ["pet accessories", "dog collar", "cat toys", "pet bandana"],
    "wedding_events": ["wedding favors", "bridesmaid gifts", "party decorations"],
    "fitness": ["gym accessories", "yoga mat", "water bottle", "resistance bands"],
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def fetch_etsy_search_suggestions(query: str) -> list:
    """
    Get Etsy's autocomplete/search suggestions for a query.
    These represent what real buyers are searching for.
    """
    url = "https://www.etsy.com/api/v3/ajax/member/search-suggestions"
    headers = {
        "User-Agent": USER_AGENTS[0],
        "Accept": "application/json",
        "Referer": "https://www.etsy.com/",
        "X-Requested-With": "XMLHttpRequest",
    }
    params = {"query": query, "type": "query_and_listing", "limit": 10}

    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            response = client.get(url, headers=headers, params=params)
            if response.status_code != 200:
                # Fallback: try the search page and extract suggestions
                return fetch_etsy_trending_from_search(query)

            data = response.json()
            suggestions = []
            for item in data.get("queries", []):
                suggestions.append(item.get("query", ""))
            return [s for s in suggestions if s]

    except Exception as e:
        logger.warning(f"Etsy suggestions API failed for '{query}': {e}")
        return fetch_etsy_trending_from_search(query)


def fetch_etsy_trending_from_search(query: str) -> list:
    """
    Fallback: extract product keywords from Etsy search results page.
    Parses listing titles to find trending product terms.
    """
    import random

    url = f"https://www.etsy.com/search"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    params = {"q": query, "ref": "search_bar", "order": "most_relevant"}

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(url, headers=headers, params=params)
            if response.status_code != 200:
                logger.warning(f"Etsy search returned {response.status_code} for '{query}'")
                return []

            soup = BeautifulSoup(response.text, "html.parser")
            keywords = set()

            # Extract from listing titles
            for title_el in soup.select("h3.v2-listing-card__title, [data-listing-card-v2] h3"):
                title = title_el.get_text(strip=True).lower()
                # Extract meaningful 2-3 word phrases
                words = re.findall(r'\b[a-z]{3,}\b', title)
                for i in range(len(words) - 1):
                    phrase = f"{words[i]} {words[i+1]}"
                    if len(phrase) >= 6:
                        keywords.add(phrase)
                    if i + 2 < len(words):
                        phrase3 = f"{words[i]} {words[i+1]} {words[i+2]}"
                        if len(phrase3) >= 10:
                            keywords.add(phrase3)

            # Also extract from search tag pills if present
            for tag in soup.select("[data-search-tag], .search-nav-tag"):
                tag_text = tag.get_text(strip=True).lower()
                if len(tag_text) >= 3:
                    keywords.add(tag_text)

            return list(keywords)[:20]

    except Exception as e:
        logger.error(f"Etsy search scrape failed for '{query}': {e}")
        return []


def _open_conn():
    """Open SQLite connection in autocommit mode with WAL + busy_timeout."""
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    return conn


def discover_from_etsy():
    """
    Discover trending product keywords from Etsy search suggestions
    and trending items across tracked categories.
    """
    # Read existing keywords once, then close
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

    # Merge DB categories with seed terms
    active_keywords = get_active_keywords()
    search_terms = {}
    for category, seeds in ETSY_SEARCH_SEEDS.items():
        search_terms[category] = seeds[:]
    for category, kws in active_keywords.items():
        if category not in search_terms:
            search_terms[category] = []
        search_terms[category].extend(kws[:3])

    discovered = 0

    for category, seeds in search_terms.items():
        for seed in seeds:
            try:
                ETSY.wait_if_needed()
            except RateLimitExceeded:
                logger.warning("Etsy rate limit reached. Stopping.")
                return discovered

            logger.info(f"Etsy discovery: searching '{seed}' ({category})")
            suggestions = fetch_etsy_search_suggestions(seed)
            ETSY.record_request()

            if not suggestions:
                time.sleep(3)
                continue

            # Open per-seed connection, write batch, close
            seed_conn = _open_conn()
            try:
                for suggestion in suggestions:
                    kw_lower = suggestion.strip().lower()
                    if not kw_lower or len(kw_lower) < 3:
                        continue
                    if kw_lower in existing or kw_lower in already_pending:
                        continue

                    try:
                        seed_conn.execute("""
                            INSERT OR IGNORE INTO pending_keywords
                            (keyword, suggested_category, source, parent_keyword, relevance_score)
                            VALUES (?, ?, 'etsy', ?, ?)
                        """, (kw_lower, category, seed, 0.6))
                        discovered += 1
                        already_pending.add(kw_lower)
                        logger.info(f"Discovered from Etsy: '{kw_lower}' (seed='{seed}')")
                    except Exception as e:
                        logger.debug(f"Failed to insert keyword '{kw_lower}': {e}")
            finally:
                seed_conn.close()

            time.sleep(3)

    logger.info(f"Etsy discovery complete. {discovered} new keywords found.")
    return discovered


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    discover_from_etsy()
