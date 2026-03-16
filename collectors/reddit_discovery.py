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
]

# Keywords that signal a product mention in a post
SIGNAL_PHRASES = [
    r"selling\s+(\w[\w\s]{2,30})\s+(?:like crazy|well|fast|great)",
    r"found\s+(?:a\s+)?(?:great|good|amazing)\s+(?:niche|product)[\s:]+(\w[\w\s]{2,30})",
    r"trending\s+(?:product|niche|item)[\s:]+(\w[\w\s]{2,30})",
    r"(?:hot|new|emerging)\s+(?:niche|product|trend)[\s:]+(\w[\w\s]{2,30})",
    r"making\s+\$?\d+[kK]?\+?\s+(?:selling|with|from)\s+(\w[\w\s]{2,30})",
    r"(?:recommend|suggest)\w*\s+(?:selling|trying)\s+(\w[\w\s]{2,30})",
    r"best\s+(?:selling|performing)\s+(\w[\w\s]{2,30})",
]

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


def extract_product_keywords(text: str) -> list:
    """Extract potential product keywords from post text using signal phrases."""
    keywords = []
    text_lower = text.lower()

    for pattern in SIGNAL_PHRASES:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            cleaned = match.strip().rstrip(".,!?;:")
            # Filter: must be 3+ chars, not all stop words
            words = cleaned.split()
            non_stop = [w for w in words if w.lower() not in STOP_WORDS]
            if len(cleaned) >= 3 and len(non_stop) > 0 and len(words) <= 5:
                keywords.append(cleaned)

    return keywords


def map_subreddit_to_category(subreddit: str, keyword: str) -> str:
    """Best-effort category mapping based on subreddit and keyword content."""
    keyword_lower = keyword.lower()

    # Keyword-based mapping
    category_hints = {
        "beauty": ["nail", "lash", "makeup", "cosmetic", "skincare", "serum", "cream", "hair"],
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


def discover_from_reddit():
    """
    Scan e-commerce subreddits for product keyword mentions.
    High-engagement posts are weighted more heavily.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    existing = set(
        row[0].lower() for row in
        conn.execute("SELECT keyword FROM keywords WHERE is_active = 1").fetchall()
    )
    already_pending = set(
        row[0].lower() for row in
        conn.execute("SELECT keyword FROM pending_keywords WHERE status = 'pending'").fetchall()
    )

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

        for post in posts:
            # Combine title and body for keyword extraction
            full_text = f"{post['title']} {post['selftext']}"
            keywords = extract_product_keywords(full_text)

            for keyword in keywords:
                kw_lower = keyword.lower()
                if kw_lower in existing or kw_lower in already_pending:
                    continue

                category = map_subreddit_to_category(subreddit, keyword)

                # Relevance score based on post engagement
                engagement = post["score"] + post["num_comments"] * 2
                relevance = min(1.0, engagement / 500)

                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO pending_keywords
                        (keyword, suggested_category, source, parent_keyword, relevance_score)
                        VALUES (?, ?, 'reddit', ?, ?)
                    """, (kw_lower, category, f"r/{subreddit}", relevance))
                    discovered += 1
                    already_pending.add(kw_lower)
                    logger.info(f"Discovered from Reddit: '{kw_lower}' (r/{subreddit}, relevance={relevance:.2f})")
                except Exception as e:
                    logger.debug(f"Failed to insert keyword '{kw_lower}': {e}")

        # Be respectful to Reddit
        time.sleep(2)

    conn.commit()
    conn.close()
    logger.info(f"Reddit discovery complete. {discovered} new keywords found.")
    return discovered


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    discover_from_reddit()
