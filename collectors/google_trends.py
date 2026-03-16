"""Google Trends data collector using pytrends. DB-driven keyword list."""

import sqlite3
import json
import time
import logging
from datetime import datetime

from pytrends.request import TrendReq

from config import DB_PATH, get_active_keywords
from rate_limiter import GOOGLE_TRENDS, RateLimitExceeded

logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def suggest_discovered_keyword(db, keyword: str, category: str, parent: str, source: str = "google_related"):
    """Add a discovered keyword to the pending_keywords table for user approval."""
    try:
        db.execute(
            """INSERT OR IGNORE INTO pending_keywords
               (keyword, suggested_category, source, parent_keyword, relevance_score, status)
               VALUES (?, ?, ?, ?, ?, 'pending')""",
            (keyword, category, source, parent, 0.5),
        )
    except Exception as e:
        logger.debug(f"Failed to suggest keyword '{keyword}': {e}")


def collect_trends():
    """Collect Google Trends data for all active keywords from DB."""
    pytrends = TrendReq(hl="en-US", tz=480)
    db = get_db()
    cursor = db.cursor()
    watchlist = get_active_keywords()
    total_collected = 0

    # Check if we have enough quota
    total_keywords = sum(len(kws) for kws in watchlist.values())
    remaining = GOOGLE_TRENDS.get_remaining_today()
    if remaining < total_keywords:
        logger.warning(f"Rate limit: {remaining} requests remaining today, {total_keywords} keywords to process")

    consecutive_429s = 0
    MAX_CONSECUTIVE_429 = 3  # Give up after 3 consecutive 429 errors
    base_delay = 60  # seconds between successful batches

    for category, keywords in watchlist.items():
        for i in range(0, len(keywords), 5):
            batch = keywords[i : i + 5]
            logger.info(f"Collecting trends for batch: {batch}")

            try:
                GOOGLE_TRENDS.wait_if_needed()
                pytrends.build_payload(batch, timeframe="today 12-m", geo="")
                interest_df = pytrends.interest_over_time()

                if interest_df.empty:
                    logger.warning(f"No interest data for batch: {batch}")
                    time.sleep(base_delay)
                    continue

                # Reset 429 counter on success
                consecutive_429s = 0

                for keyword in batch:
                    if keyword not in interest_df.columns:
                        continue

                    cursor.execute(
                        "SELECT id FROM keywords WHERE keyword = ?", (keyword,)
                    )
                    row = cursor.fetchone()
                    if not row:
                        continue
                    keyword_id = row["id"]

                    for date, score in interest_df[keyword].items():
                        date_str = date.strftime("%Y-%m-%d")
                        cursor.execute(
                            """INSERT OR REPLACE INTO trend_data
                               (keyword_id, date, interest_score, collected_at)
                               VALUES (?, ?, ?, ?)""",
                            (keyword_id, date_str, int(score), datetime.utcnow().isoformat()),
                        )
                    total_collected += len(interest_df[keyword])

                # Commit trend data now to release write lock
                db.commit()

                # Related queries: store rising and auto-discover new keywords
                try:
                    related = pytrends.related_queries()
                    for keyword in batch:
                        if keyword in related and related[keyword]["rising"] is not None:
                            rising_df = related[keyword]["rising"].head(10)
                            rising_list = rising_df["query"].tolist()

                            cursor.execute(
                                "SELECT id FROM keywords WHERE keyword = ?", (keyword,)
                            )
                            row = cursor.fetchone()
                            if row:
                                cursor.execute(
                                    """UPDATE trend_data SET related_rising = ?
                                       WHERE keyword_id = ?
                                       ORDER BY date DESC LIMIT 1""",
                                    (json.dumps(rising_list), row["id"]),
                                )

                            # Auto-discover: suggest rising keywords not already tracked
                            existing = set(kw for kws in watchlist.values() for kw in kws)
                            for rising_kw in rising_list:
                                if rising_kw.lower() not in {e.lower() for e in existing}:
                                    suggest_discovered_keyword(
                                        db, rising_kw, category, keyword, "google_related"
                                    )
                                    logger.info(f"Discovered keyword: '{rising_kw}' (from '{keyword}')")

                except Exception as e:
                    logger.warning(f"Failed to get related queries: {e}")

                # Regional interest
                try:
                    pytrends.build_payload(batch[:1], timeframe="today 12-m", geo="")
                    region_df = pytrends.interest_by_region(
                        resolution="COUNTRY", inc_low_vol=True, inc_geo_code=True
                    )
                    if not region_df.empty:
                        kw = batch[0]
                        top_regions = (
                            region_df[kw]
                            .sort_values(ascending=False)
                            .head(20)
                            .to_dict()
                        )
                        cursor.execute(
                            "SELECT id FROM keywords WHERE keyword = ?", (kw,)
                        )
                        row = cursor.fetchone()
                        if row:
                            cursor.execute(
                                """UPDATE trend_data SET region_data = ?
                                   WHERE keyword_id = ?
                                   ORDER BY date DESC LIMIT 1""",
                                (json.dumps(top_regions), row["id"]),
                            )
                except Exception as e:
                    logger.warning(f"Failed to get regional data: {e}")

                db.commit()
                GOOGLE_TRENDS.record_request()

            except RateLimitExceeded as e:
                logger.warning(f"Stopping collection: {e}")
                db.close()
                return total_collected
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg:
                    consecutive_429s += 1
                    if consecutive_429s >= MAX_CONSECUTIVE_429:
                        logger.error(
                            f"Google is blocking requests ({consecutive_429s} consecutive 429s). "
                            f"Stopping Google Trends collector. Try again in a few hours."
                        )
                        db.close()
                        return total_collected
                    # Exponential backoff: 2min, 4min, 8min...
                    backoff = base_delay * (2 ** consecutive_429s)
                    logger.warning(
                        f"429 rate limit ({consecutive_429s}/{MAX_CONSECUTIVE_429}). "
                        f"Backing off {backoff}s..."
                    )
                    time.sleep(backoff)
                    continue
                else:
                    logger.error(f"Error collecting trends for {batch}: {e}")
                    time.sleep(5)

            logger.info(f"Sleeping {base_delay}s for rate limiting...")
            time.sleep(base_delay)

    db.close()
    logger.info(f"Google Trends collection complete. {total_collected} data points stored.")
    return total_collected


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if "--test" in sys.argv:
        logger.info("Running test collection (first batch only)...")
        pytrends = TrendReq(hl="en-US", tz=480)
        watchlist = get_active_keywords()
        if watchlist:
            test_keywords = list(watchlist.values())[0][:5]
            pytrends.build_payload(test_keywords, timeframe="today 3-m", geo="")
            df = pytrends.interest_over_time()
            if not df.empty:
                print(df.tail())
                print("Test passed.")
            else:
                print("No data returned.")
        else:
            print("No keywords in database. Run seed_watchlist.py first.")
    else:
        collect_trends()
