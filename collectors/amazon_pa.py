"""Amazon Product Advertising API collector."""

import sqlite3
import json
import logging
from datetime import datetime

from config import (
    DB_PATH,
    AMAZON_ACCESS_KEY,
    AMAZON_SECRET_KEY,
    AMAZON_PARTNER_TAG,
    get_active_keywords,
)

logger = logging.getLogger(__name__)

# Lazy import: paapi5 may not be installed
try:
    from amazon_paapi import AmazonApi
    HAS_PAAPI = True
except ImportError:
    HAS_PAAPI = False
    logger.warning("amazon-paapi not installed. Amazon PA-API collector disabled.")


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def get_amazon_api():
    """Initialize the Amazon PA-API client."""
    if not HAS_PAAPI:
        return None
    if not all([AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY, AMAZON_PARTNER_TAG]):
        logger.warning("Amazon PA-API credentials not configured.")
        return None

    return AmazonApi(
        AMAZON_ACCESS_KEY,
        AMAZON_SECRET_KEY,
        AMAZON_PARTNER_TAG,
        country="US",
    )


def search_products(keyword: str, category: str, max_results: int = 10):
    """Search Amazon for products matching a keyword."""
    api = get_amazon_api()
    if not api:
        return []

    try:
        results = api.search_items(
            keywords=keyword,
            search_index="All",
            item_count=min(max_results, 10),
            resources=[
                "ItemInfo.Title",
                "ItemInfo.ByLineInfo",
                "Offers.Listings.Price",
                "Offers.Listings.DeliveryInfo.IsFreeShippingEligible",
                "Images.Primary.Large",
                "BrowseNodeInfo.BrowseNodes.SalesRank",
            ],
        )

        products = []
        for item in results.items or []:
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

            if item.offers and item.offers.listings:
                listing = item.offers.listings[0]
                if listing.price:
                    product["price"] = listing.price.amount

            if item.images and item.images.primary and item.images.primary.large:
                product["image_url"] = item.images.primary.large.url

            products.append(product)

        return products

    except Exception as e:
        logger.error(f"Amazon search failed for '{keyword}': {e}")
        return []


def collect_amazon_products():
    """Collect product data from Amazon for all watchlist keywords."""
    db = get_db()
    cursor = db.cursor()
    total_collected = 0

    watchlist = get_active_keywords()
    for category, keywords in watchlist.items():
        for keyword in keywords[:3]:  # Limit to top 3 per category to conserve API calls
            logger.info(f"Searching Amazon for: {keyword} ({category})")
            products = search_products(keyword, category)

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
    return total_collected


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if "--test" in sys.argv:
        logger.info("Running Amazon PA-API test...")
        results = search_products("nail stickers", "beauty", max_results=3)
        for r in results:
            print(f"  {r['asin']}: {r['title'][:60]} - ${r['price']}")
        if results:
            print("Test passed.")
        else:
            print("No results. Check API credentials.")
    else:
        collect_amazon_products()
