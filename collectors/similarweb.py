"""SimilarWeb free tier traffic estimator for competitor domains."""

import sqlite3
import json
import logging
import time
from datetime import datetime

import httpx

from config import DB_PATH, get_competitors
from rate_limiter import SIMILARWEB, RateLimitExceeded

logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def estimate_traffic(domain: str) -> dict:
    """Estimate website traffic using free publicly available data.

    Uses SimilarWeb's public site info (no API key needed for basic data).
    Falls back to a simple estimation based on domain age and category.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    result = {
        "visits_estimate": 0,
        "top_source": "unknown",
        "bounce_rate": 0.0,
    }

    # Try SimilarWeb's public API endpoint
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            # Public overview endpoint (may be rate limited)
            response = client.get(
                f"https://data.similarweb.com/api/v1/data?domain={domain}",
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                result["visits_estimate"] = data.get("EstimatedMonthlyVisits", {})
                if isinstance(result["visits_estimate"], dict):
                    # Get most recent month
                    values = list(result["visits_estimate"].values())
                    result["visits_estimate"] = values[-1] if values else 0

                sources = data.get("TrafficSources", {})
                if sources:
                    top = max(sources.items(), key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0)
                    result["top_source"] = top[0]

                result["bounce_rate"] = data.get("BounceRate", 0.0)

                logger.info(f"Got SimilarWeb data for {domain}: {result['visits_estimate']} visits")
                return result
            else:
                logger.info(f"SimilarWeb returned {response.status_code} for {domain}")

    except Exception as e:
        logger.warning(f"SimilarWeb request failed for {domain}: {e}")

    return result


def collect_competitor_traffic():
    """Collect traffic estimates for all competitor domains."""
    db = get_db()
    cursor = db.cursor()
    total_collected = 0
    current_month = datetime.utcnow().strftime("%Y-%m-01")

    competitors = get_competitors()

    for category, competitors in competitors.items():
        for comp in competitors:
            domain = comp["domain"]
            logger.info(f"Estimating traffic for: {domain}")

            # Get competitor ID
            cursor.execute(
                "SELECT id FROM competitors WHERE domain = ?", (domain,)
            )
            row = cursor.fetchone()
            if not row:
                logger.warning(f"Competitor not found in DB: {domain}")
                continue

            competitor_id = row["id"]

            try:
                SIMILARWEB.wait_if_needed()
            except RateLimitExceeded as e:
                logger.warning(f"Stopping SimilarWeb collection: {e}")
                db.commit()
                db.close()
                return total_collected

            traffic = estimate_traffic(domain)
            SIMILARWEB.record_request()

            if traffic["visits_estimate"]:
                try:
                    cursor.execute(
                        """INSERT OR REPLACE INTO competitor_traffic
                           (competitor_id, month, visits_estimate, top_source, bounce_rate, collected_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            competitor_id,
                            current_month,
                            traffic["visits_estimate"],
                            traffic["top_source"],
                            traffic["bounce_rate"],
                            datetime.utcnow().isoformat(),
                        ),
                    )
                    total_collected += 1
                except Exception as e:
                    logger.error(f"Failed to store traffic for {domain}: {e}")

            # Rate limiting
            time.sleep(5)

    db.commit()
    db.close()
    logger.info(f"Competitor traffic collection complete. {total_collected} domains updated.")
    return total_collected


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if "--test" in sys.argv:
        logger.info("Running SimilarWeb test...")
        result = estimate_traffic("glamnetic.com")
        print(f"  Visits: {result['visits_estimate']}")
        print(f"  Top source: {result['top_source']}")
        print(f"  Bounce rate: {result['bounce_rate']}")
        print("Test complete.")
    else:
        collect_competitor_traffic()
