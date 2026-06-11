"""Amazon product data collector — Creators API (preferred) or legacy PA-API.

Amazon replaced the Product Advertising API with the Creators API in 2025.
New Associates accounts get OAuth2-style credentials (credential id +
secret + version) instead of the old AWS-style access/secret keys. This
collector supports both: Creators API when its credentials are configured,
legacy PA-API otherwise.
"""

import sqlite3
import json
import logging
from datetime import datetime

from config import (
    DB_PATH,
    AMAZON_ACCESS_KEY,
    AMAZON_SECRET_KEY,
    AMAZON_PARTNER_TAG,
    AMAZON_CREATORS_CREDENTIAL_ID,
    AMAZON_CREATORS_CREDENTIAL_SECRET,
    AMAZON_CREATORS_VERSION,
    get_active_keywords,
)
from rate_limiter import AMAZON_PA, RateLimitExceeded

logger = logging.getLogger(__name__)

# Lazy imports: the package may not be installed
try:
    from amazon_creatorsapi import AmazonCreatorsApi
    HAS_CREATORS = True
except ImportError:
    HAS_CREATORS = False

try:
    from amazon_paapi import AmazonApi
    HAS_PAAPI = True
except ImportError:
    HAS_PAAPI = False

if not HAS_CREATORS and not HAS_PAAPI:
    logger.warning("python-amazon-paapi not installed. Amazon collector disabled.")


def _has_creators_creds() -> bool:
    return all([
        AMAZON_CREATORS_CREDENTIAL_ID,
        AMAZON_CREATORS_CREDENTIAL_SECRET,
        AMAZON_PARTNER_TAG,
    ])


def _has_legacy_creds() -> bool:
    return all([AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY, AMAZON_PARTNER_TAG])


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def get_amazon_api():
    """Initialize the Amazon API client.

    Returns (client, flavor) where flavor is "creators" or "paapi",
    or (None, None) if not configured/installed.
    """
    if HAS_CREATORS and _has_creators_creds():
        return (
            AmazonCreatorsApi(
                AMAZON_CREATORS_CREDENTIAL_ID,
                AMAZON_CREATORS_CREDENTIAL_SECRET,
                AMAZON_CREATORS_VERSION,
                AMAZON_PARTNER_TAG,
            ),
            "creators",
        )

    if HAS_PAAPI and _has_legacy_creds():
        return (
            AmazonApi(
                AMAZON_ACCESS_KEY,
                AMAZON_SECRET_KEY,
                AMAZON_PARTNER_TAG,
                country="US",
            ),
            "paapi",
        )

    logger.warning("Amazon API credentials not configured.")
    return (None, None)


def _item_to_product(item, flavor: str) -> dict:
    """Normalize an API item (either flavor) into our product dict."""
    product = {
        "asin": item.asin,
        "title": item.item_info.title.display_value if item.item_info and item.item_info.title else "",
        "brand": "",
        "price": None,
        "image_url": "",
        "sales_rank": None,
    }

    if item.item_info and item.item_info.by_line_info and item.item_info.by_line_info.brand:
        product["brand"] = item.item_info.by_line_info.brand.display_value

    if flavor == "creators":
        # Creators API: item.offers_v2.listings[0].price.money.amount
        offers = getattr(item, "offers_v2", None)
        if offers and offers.listings:
            price = offers.listings[0].price
            if price and price.money and price.money.amount is not None:
                product["price"] = float(price.money.amount)
    else:
        # Legacy PA-API: item.offers.listings[0].price.amount
        offers = getattr(item, "offers", None)
        if offers and offers.listings and offers.listings[0].price:
            product["price"] = offers.listings[0].price.amount

    if item.images and item.images.primary and item.images.primary.large:
        product["image_url"] = item.images.primary.large.url

    return product


# Resource selections per API flavor (Creators API uses camelCase paths
# typed as a SearchItemsResource enum)
if HAS_CREATORS:
    from amazon_creatorsapi.models import SearchItemsResource

    _CREATORS_RESOURCES = [
        SearchItemsResource("itemInfo.title"),
        SearchItemsResource("itemInfo.byLineInfo"),
        SearchItemsResource("offersV2.listings.price"),
        SearchItemsResource("images.primary.large"),
    ]
else:
    _CREATORS_RESOURCES = []
_PAAPI_RESOURCES = [
    "ItemInfo.Title",
    "ItemInfo.ByLineInfo",
    "Offers.Listings.Price",
    "Offers.Listings.DeliveryInfo.IsFreeShippingEligible",
    "Images.Primary.Large",
    "BrowseNodeInfo.BrowseNodes.SalesRank",
]


def search_products(keyword: str, category: str, max_results: int = 10):
    """Search Amazon for products matching a keyword."""
    api, flavor = get_amazon_api()
    if not api:
        return []

    try:
        AMAZON_PA.wait_if_needed()
        results = api.search_items(
            keywords=keyword,
            search_index="All",
            item_count=min(max_results, 10),
            resources=_CREATORS_RESOURCES if flavor == "creators" else _PAAPI_RESOURCES,
        )
        AMAZON_PA.record_request()

        return [_item_to_product(item, flavor) for item in results.items or []]

    except RateLimitExceeded:
        raise  # caller stops the run; don't swallow as a search failure
    except Exception as e:
        logger.error(f"Amazon search failed for '{keyword}': {e}")
        return []


def collect_amazon_products():
    """Collect product data from Amazon for all watchlist keywords.

    Returns (success: bool, price_snapshots_written: int, error: str | None).
    Never raises to the scheduler.
    """
    if not HAS_CREATORS and not HAS_PAAPI:
        return (True, 0, "python-amazon-paapi package not installed")
    if not (_has_creators_creds() or _has_legacy_creds()):
        # Skip reason (not None) so the stall guard doesn't fire while
        # credentials are simply not configured yet.
        logger.warning("Amazon API credentials not configured; skipping.")
        return (True, 0, "Amazon API credentials not configured")

    db = get_db()
    cursor = db.cursor()
    total_collected = 0

    watchlist = get_active_keywords()
    for category, keywords in watchlist.items():
        for keyword in keywords[:3]:  # Limit to top 3 per category to conserve API calls
            logger.info(f"Searching Amazon for: {keyword} ({category})")
            try:
                products = search_products(keyword, category)
            except RateLimitExceeded as e:
                logger.warning(f"Stopping PA-API collection: {e}")
                db.commit()
                db.close()
                return (True, total_collected, str(e))

            for prod in products:
                if not prod["asin"]:
                    continue

                # Get keyword_id
                cursor.execute(
                    "SELECT id FROM keywords WHERE keyword = ?", (keyword,)
                )
                kw_row = cursor.fetchone()
                keyword_id = kw_row["id"] if kw_row else None

                # Upsert product
                cursor.execute(
                    """INSERT INTO products (asin, title, category, brand, keyword_id, image_url)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(asin) DO UPDATE SET
                           title = excluded.title,
                           brand = excluded.brand,
                           image_url = excluded.image_url""",
                    (
                        prod["asin"],
                        prod["title"],
                        category,
                        prod["brand"],
                        keyword_id,
                        prod["image_url"],
                    ),
                )

                # Store price snapshot if available
                if prod["price"]:
                    cursor.execute(
                        "SELECT id FROM products WHERE asin = ?", (prod["asin"],)
                    )
                    product_id = cursor.fetchone()["id"]
                    cursor.execute(
                        """INSERT INTO product_history
                           (product_id, date, price, sales_rank, collected_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (
                            product_id,
                            datetime.utcnow().isoformat(),
                            prod["price"],
                            prod["sales_rank"],
                            datetime.utcnow().isoformat(),
                        ),
                    )
                    total_collected += 1

            db.commit()

    db.close()
    logger.info(f"Amazon PA-API collection complete. {total_collected} products collected.")
    return (True, total_collected, None)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if "--test" in sys.argv:
        _, flavor = get_amazon_api()
        logger.info(f"Running Amazon API test (flavor: {flavor or 'not configured'})...")
        results = search_products("nail stickers", "beauty", max_results=3)
        for r in results:
            print(f"  {r['asin']}: {r['title'][:60]} - ${r['price']}")
        if results:
            print("Test passed.")
        else:
            print("No results. Check API credentials.")
    else:
        collect_amazon_products()
