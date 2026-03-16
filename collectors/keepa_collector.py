"""Keepa API collector for Amazon product data."""

import sqlite3
import json
import logging
from datetime import datetime

import keepa

from config import DB_PATH, KEEPA_API_KEY, get_tracked_asins
from rate_limiter import KEEPA_API, RateLimitExceeded

logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def collect_products():
    """Collect price, rank, and stock data for tracked ASINs via Keepa."""
    if not KEEPA_API_KEY:
        logger.warning("KEEPA_API_KEY not set, skipping collection.")
        return 0

    api = keepa.Keepa(KEEPA_API_KEY)
    db = get_db()
    cursor = db.cursor()
    total_collected = 0

    tracked = get_tracked_asins()
    for category, asins in tracked.items():
        if not asins:
            logger.info(f"No ASINs configured for {category}, skipping.")
            continue

        logger.info(f"Collecting Keepa data for {len(asins)} ASINs in {category}")

        try:
            KEEPA_API.wait_if_needed()
            products = api.query(asins, domain="US", history=True)
            KEEPA_API.record_request()

            for product in products:
                asin = product.get("asin", "")
                title = product.get("title", "")
                brand = product.get("brand", "")
                image_url = ""
                images = product.get("imagesCSV", "")
                if images:
                    image_url = f"https://images-na.ssl-images-amazon.com/images/I/{images.split(',')[0]}"

                # Upsert product record
                cursor.execute(
                    """INSERT INTO products (asin, title, category, brand, image_url)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(asin) DO UPDATE SET
                           title = excluded.title,
                           brand = excluded.brand,
                           image_url = excluded.image_url""",
                    (asin, title, category, brand, image_url),
                )

                cursor.execute(
                    "SELECT id FROM products WHERE asin = ?", (asin,)
                )
                product_id = cursor.fetchone()["id"]

                # Extract latest data points from Keepa history
                current_price = _get_latest_keepa_value(product, "csv", index=0)  # Amazon price
                buy_box_price = _get_latest_keepa_value(product, "csv", index=18)  # Buy box
                sales_rank = _get_latest_keepa_value(product, "csv", index=3)  # Sales rank
                offers_count = _get_latest_keepa_value(product, "csv", index=11)  # New offer count

                rating = product.get("csv", [[]])[16]  # Rating history
                rating_val = rating[-1] / 10.0 if rating and len(rating) > 0 and rating[-1] else None

                review_count = product.get("csv", [[]])[17]  # Review count history
                review_val = review_count[-1] if review_count and len(review_count) > 0 else None

                # Determine stock status
                stock_status = "in_stock"
                if current_price is None or current_price < 0:
                    stock_status = "out_of_stock"
                elif offers_count is not None and offers_count <= 2:
                    stock_status = "low_stock"

                # Convert Keepa price (cents) to dollars
                if current_price and current_price > 0:
                    current_price = current_price / 100.0
                else:
                    current_price = None

                if buy_box_price and buy_box_price > 0:
                    buy_box_price = buy_box_price / 100.0
                else:
                    buy_box_price = None

                cursor.execute(
                    """INSERT INTO product_history
                       (product_id, date, price, sales_rank, rating, review_count,
                        offers_count, buy_box_price, stock_status, collected_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        product_id,
                        datetime.utcnow().isoformat(),
                        current_price,
                        sales_rank,
                        rating_val,
                        review_val,
                        offers_count,
                        buy_box_price,
                        stock_status,
                        datetime.utcnow().isoformat(),
                    ),
                )
                total_collected += 1
                logger.info(f"Collected data for {asin}: ${current_price}, rank={sales_rank}")

            db.commit()

        except RateLimitExceeded as e:
            logger.warning(f"Stopping Keepa collection: {e}")
            db.close()
            return total_collected
        except Exception as e:
            logger.error(f"Error collecting Keepa data for {category}: {e}")
            db.rollback()

    db.close()
    logger.info(f"Keepa collection complete. {total_collected} products updated.")
    return total_collected


def discover_new_products(category: str, search_term: str, max_results: int = 20):
    """Use Keepa to discover new products entering a category."""
    if not KEEPA_API_KEY:
        return []

    api = keepa.Keepa(KEEPA_API_KEY)

    try:
        product_search = api.product_finder(
            {
                "title": search_term,
                "sort": ["current_SALES", "asc"],
                "perPage": max_results,
            }
        )
        return product_search if product_search else []
    except Exception as e:
        logger.error(f"Product discovery failed for '{search_term}': {e}")
        return []


def detect_anomalies():
    """Detect price drops and stock-outs on tracked products."""
    db = get_db()
    cursor = db.cursor()
    anomalies = []

    cursor.execute(
        """SELECT p.id, p.asin, p.title, p.category,
                  ph1.price as current_price, ph1.stock_status,
                  ph2.price as prev_price
           FROM products p
           JOIN product_history ph1 ON p.id = ph1.product_id
           LEFT JOIN product_history ph2 ON p.id = ph2.product_id
               AND ph2.date < ph1.date
           WHERE p.is_active = 1
           ORDER BY ph1.date DESC, ph2.date DESC"""
    )

    seen = set()
    for row in cursor.fetchall():
        if row["id"] in seen:
            continue
        seen.add(row["id"])

        # Check for price drops > 15%
        if row["current_price"] and row["prev_price"] and row["prev_price"] > 0:
            drop_pct = ((row["prev_price"] - row["current_price"]) / row["prev_price"]) * 100
            if drop_pct > 15:
                anomalies.append({
                    "type": "price_drop",
                    "asin": row["asin"],
                    "title": row["title"],
                    "category": row["category"],
                    "drop_pct": round(drop_pct, 1),
                    "current_price": row["current_price"],
                    "prev_price": row["prev_price"],
                })

        # Check for stock-outs
        if row["stock_status"] == "out_of_stock":
            anomalies.append({
                "type": "stock_out",
                "asin": row["asin"],
                "title": row["title"],
                "category": row["category"],
            })

    db.close()
    return anomalies


def _get_latest_keepa_value(product: dict, key: str, index: int):
    """Extract the latest value from a Keepa CSV history array."""
    try:
        csv_data = product.get(key, [])
        if csv_data and len(csv_data) > index and csv_data[index]:
            values = csv_data[index]
            if isinstance(values, list) and len(values) >= 2:
                # Keepa format: [time1, val1, time2, val2, ...]
                return values[-1]
        return None
    except (IndexError, TypeError):
        return None


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if "--test" in sys.argv:
        logger.info("Running Keepa test...")
        if KEEPA_API_KEY:
            api = keepa.Keepa(KEEPA_API_KEY)
            tokens = api.tokens_left
            print(f"Keepa tokens remaining: {tokens}")
            print("Test passed.")
        else:
            print("KEEPA_API_KEY not set. Set it and retry.")
    else:
        collect_products()
