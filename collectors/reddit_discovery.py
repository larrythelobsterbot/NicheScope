"""
NicheScope Reddit Discovery
=============================
Monitors e-commerce subreddits for trending product keywords
and niche signals using Reddit's public JSON API.

No API key needed — uses the .json endpoint on public subreddits.
"""

import sqlite3
import re
import time
import logging
from datetime import datetime

import httpx

from config import DB_PATH, get_active_keywords
from rate_limiter import RateLimiter, RateLimitExceeded

logger = logging.getLogger(__name__)

# Reddit rate limiter: be very conservative
REDDIT = RateLimiter(
    service_name="reddit",
    requests_per_minute=10,  # Reddit allows ~60/min for public JSON but be safe
    daily_limit=500
)

# Subreddits to monitor for e-commerce/product signals
DISCOVERY_SUBREDDITS = [
    "dropshipping",
    "AmazonFBA",
    "FulfillmentByAmazon",
    "Etsy",
    "ecommerce",
    "Entrepreneur",
    "smallbusiness",
    "juststart",
    "SideProject",
    "passive_income",
    "AsianBeauty",
    "AusSkincare",
    "SkincareAddictionUK",
]

# Patterns for dropshipping/FBA community posts
SIGNAL_PHRASES = [
    r"selling\s+(\w[\w\s]{2,30})\s+(?:like crazy|well|fast|great)",
    r"found\s+(?:a\s+)?(?:great|good|amazing)\s+(?:niche|product)[\s:]+(\w[\w\s]{2,30})",
    r"trending\s+(?:product|niche|item)[\s:]+(\w[\w\s]{2,30})",
    r"(?:hot|new|emerging)\s+(?:niche|product|trend)[\s:]+(\w[\w\s]{2,30})",
    r"making\s+\$?\d+[kK]?\+?\s+(?:selling|with|from)\s+(\w[\w\s]{2,30})",
    r"(?:recommend|suggest)\w*\s+(?:selling|trying)\s+(\w[\w\s]{2,30})",
    r"best\s+(?:selling|performing)\s+(\w[\w\s]{2,30})",
]

# Beauty/skincare product type keywords
BEAUTY_PRODUCT_TYPES = [
    "serum", "ampoule", "essence", "toner", "cream", "lotion", "oil",
    "sunscreen", "spf", "cleanser", "foam", "balm", "mask", "peel",
    "patch", "exfoliant", "moisturizer", "moisturiser", "primer",
    "concealer", "foundation", "tint", "gel", "milk", "scrub",
]
BEAUTY_BRANDS_KNOWN = [
    "numbuzin", "medicube", "beauty of joseon", "skin1004", "cosrx",
    "anua", "haruharu", "isntree", "purito", "round lab", "etude",
    "innisfree", "laneige", "missha", "klairs", "torriden", "abib",
    "dr ceuracle", "by wishtrend", "axis-y", "mary & may", "i'm from",
    "ohlolly", "tirtir", "rom&nd", "peripera", "clio", "hera", "sulwhasoo",
]

BEAUTY_PRODUCT_PATTERN = re.compile(
    r"\b([a-z][a-z0-9\s&'\-]{2,28}\s+(?:" + "|".join(BEAUTY_PRODUCT_TYPES) + r"))\b",
    re.IGNORECASE,
)
BEAUTY_BRAND_PATTERN = re.compile(
    r"\b((?:" + "|".join(re.escape(b) for b in BEAUTY_BRANDS_KNOWN) + r")\s+[a-z0-9][a-z0-9\s'\-\.]{1,30})\b",
    re.IGNORECASE,
)

# Words to filter out (too generic)
STOP_WORDS = {
    "the", "this", "that", "these", "those", "they", "them", "their",
    "product", "products", "niche", "niches", "item", "items", "thing", "things",
    "money", "business", "store", "shop", "website", "brand", "market",
    "anyone", "everyone", "someone", "something", "anything", "nothing",
    "really", "actually", "basically", "literally", "definitely",
    "amazon", "etsy", "shopify", "ebay", "alibaba", "walmart",
}


def fetch_subreddit_posts(subreddit: str, sort: str = "hot", limit: int = 25) -> list:
    """Fetch posts from a subreddit using the public JSON API."""
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    headers = {
        "User-Agent": "NicheScope/1.0 (e-commerce research tool)",
    }
    params = {"limit": limit, "raw_json": 1}

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            posts = []
            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                posts.append({
                    "title": post.get("title", ""),
                    "selftext": post.get("selftext", "")[:1000],  # Limit text size
                    "score": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                    "subreddit": subreddit,
                    "url": f"https://reddit.com{post.get('permalink', '')}",
                    "created_utc": post.get("created_utc", 0),
                })
            return posts

    except httpx.HTTPError as e:
        logger.error(f"Reddit API error for r/{subreddit}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching r/{subreddit}: {e}")
        return []


BEAUTY_SUBREDDITS = {"asianbeauty", "ausskincare", "skincareaddictionuk",
                     "skincareaddiction", "30plusskincare"}


def extract_product_keywords(text: str, subreddit: str = "") -> list:
    """Extract potential product keywords from post text.

    Uses beauty-specific patterns for beauty subreddits, dropshipping signal
    phrases for everything else.
    """
    keywords = []
    text_lower = text.lower()

    is_beauty = subreddit.lower() in BEAUTY_SUBREDDITS

    if is_beauty:
        # 1. Brand-name based: "numbuzin no 9 toner" → captured
        for match in BEAUTY_BRAND_PATTERN.finditer(text_lower):
            cleaned = match.group(1).strip().rstrip(".,!?;:()[]")
            cleaned = re.sub(r"\s+", " ", cleaned)
            if 4 <= len(cleaned) <= 60 and len(cleaned.split()) <= 6:
                keywords.append(cleaned)

        # 2. Generic "X serum/toner/cream/etc" — captures category-level mentions
        for match in BEAUTY_PRODUCT_PATTERN.finditer(text_lower):
            cleaned = match.group(1).strip().rstrip(".,!?;:()[]")
            cleaned = re.sub(r"\s+", " ", cleaned)
            words = cleaned.split()
            # Skip if all leading words are stopwords/junk
            non_stop = [w for w in words if w not in STOP_WORDS]
            if 4 <= len(cleaned) <= 50 and len(words) <= 5 and len(non_stop) >= 2:
                keywords.append(cleaned)
    else:
        # Dropshipping/FBA signal phrases for non-beauty subs
        for pattern in SIGNAL_PHRASES:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                cleaned = match.strip().rstrip(".,!?;:")
                words = cleaned.split()
                non_stop = [w for w in words if w.lower() not in STOP_WORDS]
                if len(cleaned) >= 3 and len(non_stop) > 0 and len(words) <= 5:
                    keywords.append(cleaned)

    return keywords


def map_subreddit_to_category(subreddit: str, keyword: str) -> str:
    """Best-effort category mapping based on subreddit and keyword content."""
    keyword_lower = keyword.lower()
    sub_lower = subreddit.lower()

    # Subreddit-driven defaults take priority
    if sub_lower in BEAUTY_SUBREDDITS:
        return "beauty"

    # Keyword-based mapping
    category_hints = {
        "beauty": ["nail", "lash", "makeup", "cosmetic", "skincare", "serum",
                   "cream", "hair", "toner", "ampoule", "essence", "sunscreen",
                   "cleanser", "moisturiz", "moisturis"],
        "jewelry": ["ring", "necklace", "bracelet", "earring", "pendant", "chain", "jewelry", "jewel"],
        "travel": ["luggage", "suitcase", "travel", "packing", "backpack", "passport"],
        "pets": ["pet", "dog", "cat", "collar", "leash", "treat", "toy"],
        "home": ["home", "kitchen", "garden", "decor", "furniture", "organiz", "storage"],
        "fitness": ["gym", "fitness", "yoga", "workout", "exercise", "protein", "supplement"],
        "tech_accessories": ["phone", "case", "charger", "cable", "headphone", "earbuds", "tech", "gadget"],
        "food": ["snack", "coffee", "tea", "chocolate", "candy", "sauce", "spice"],
    }

    for category, hints in category_hints.items():
        if any(h in keyword_lower for h in hints):
            return category

    return "general"


def _open_conn():
    """Open a connection in autocommit mode with WAL + busy_timeout."""
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    return conn


def discover_from_reddit():
    """
    Scan e-commerce subreddits for product keyword mentions.
    High-engagement posts are weighted more heavily.

    Uses autocommit mode to avoid holding long-running write locks while
    other rate-limiter connections also need to write.
    """
    # Read existing keywords once, then close (releases any read lock immediately)
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

    for subreddit in DISCOVERY_SUBREDDITS:
        try:
            REDDIT.wait_if_needed()
        except RateLimitExceeded:
            logger.warning("Reddit rate limit reached. Stopping.")
            break

        logger.info(f"Scanning r/{subreddit}...")
        posts = fetch_subreddit_posts(subreddit, sort="hot", limit=25)
        REDDIT.record_request()

        # Open per-subreddit connection, write batch, close
        sub_conn = _open_conn()
        try:
            for post in posts:
                full_text = f"{post['title']} {post['selftext']}"
                keywords = extract_product_keywords(full_text, subreddit)

                for keyword in keywords:
                    kw_lower = keyword.lower()
                    if kw_lower in existing or kw_lower in already_pending:
                        continue

                    category = map_subreddit_to_category(subreddit, keyword)
                    engagement = post["score"] + post["num_comments"] * 2
                    relevance = min(1.0, engagement / 500)

                    try:
                        sub_conn.execute("""
                            INSERT OR IGNORE INTO pending_keywords
                            (keyword, suggested_category, source, parent_keyword, relevance_score)
                            VALUES (?, ?, 'reddit', ?, ?)
                        """, (kw_lower, category, f"r/{subreddit}", relevance))
                        discovered += 1
                        already_pending.add(kw_lower)
                        logger.info(f"Discovered from Reddit: '{kw_lower}' (r/{subreddit}, relevance={relevance:.2f})")
                    except Exception as e:
                        logger.debug(f"Failed to insert keyword '{kw_lower}': {e}")
        finally:
            sub_conn.close()

        # Be respectful to Reddit
        time.sleep(2)

    logger.info(f"Reddit discovery complete. {discovered} new keywords found.")
    return discovered


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    discover_from_reddit()
