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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    result = {"visits_estimate": 0, "top_source": "unknown", "bounce_rate": 0.0}

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(
            f"https://data.similarweb.com/api/v1/data?domain={domain}",
            headers=headers,
        )
        if response.status_code in (429,) or 500 <= response.status_code < 600:
            raise RuntimeError(f"retryable status {response.status_code}")
        if response.status_code != 200:
            logger.info(f"SimilarWeb returned {response.status_code} for {domain}")
            return result

        data = response.json()
        est = data.get("EstimatedMonthlyVisits", {})
        if isinstance(est, dict) and est:
            result["visits_estimate"] = list(est.values())[-1]
        elif isinstance(est, (int, float)):
            result["visits_estimate"] = est

        sources = data.get("TrafficSources", {})
        if sources:
            top = max(
                sources.items(),
                key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0,
            )
            result["top_source"] = top[0]
        result["bounce_rate"] = data.get("BounceRate", 0.0)
        logger.info(f"SimilarWeb data for {domain}: {result['visits_estimate']} visits")
        return result


def estimate_traffic_with_retry(domain: str) -> dict:
    """Wrap estimate_traffic with one retry on 429/5xx or network exceptions."""
    try:
        return estimate_traffic(domain)
    except Exception:
        pass

    # retry after 5s
    time.sleep(5)
    try:
        return estimate_traffic(domain)
    except Exception as e:
        logger.warning(f"SimilarWeb final failure for {domain}: {e}")
        return {"visits_estimate": 0, "top_source": "unknown", "bounce_rate": 0.0}


def collect_competitor_traffic():
    """Collect traffic estimates for all competitor domains.

    Returns (success, items_written, error | None). Never raises.
    Writes a row for every attempted domain, even when visits_estimate=0 —
    a zero value is a valid "low-traffic" signal and preserves trend continuity
    when the public endpoint returns empty.
    """
    try:
        db = get_db()
        cursor = db.cursor()
        total_collected = 0
        current_month = datetime.utcnow().strftime("%Y-%m-01")

        competitors_by_cat = get_competitors()
        for _cat, comp_list in competitors_by_cat.items():
            for comp in comp_list:
                domain = comp["domain"]
                logger.info(f"Estimating traffic for: {domain}")

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
                    return (True, total_collected, None)

                traffic = estimate_traffic_with_retry(domain)
                SIMILARWEB.record_request()

                cursor.execute(
                    """INSERT OR REPLACE INTO competitor_traffic
                           (competitor_id, month, visits_estimate, top_source,
                            bounce_rate, collected_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        competitor_id,
                        current_month,
                        int(traffic["visits_estimate"] or 0),
                        traffic["top_source"],
                        traffic["bounce_rate"],
                        datetime.utcnow().isoformat(),
                    ),
                )
                total_collected += 1
                db.commit()  # commit per row so partial runs are preserved
                time.sleep(5)

        db.close()
        logger.info(f"SimilarWeb collection complete: {total_collected} rows written")
        return (True, total_collected, None)
    except Exception as e:
        logger.error(f"collect_competitor_traffic top-level error: {e}", exc_info=True)
        return (False, 0, str(e))


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if "--test" in sys.argv:
        logger.info("Running SimilarWeb test...")
        result = estimate_traffic_with_retry("glamnetic.com")
        print(f"  Visits: {result['visits_estimate']}")
        print(f"  Top source: {result['top_source']}")
        print(f"  Bounce rate: {result['bounce_rate']}")
        print("Test complete.")
    else:
        success, count, err = collect_competitor_traffic()
        print(f"success={success} count={count} err={err}")
