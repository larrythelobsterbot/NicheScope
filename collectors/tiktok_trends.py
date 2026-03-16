"""TikTok Creative Center trends scraper."""

import sqlite3
import json
import logging
import time
from datetime import datetime

import httpx

from config import DB_PATH, get_active_keywords
from rate_limiter import TIKTOK, RateLimitExceeded

logger = logging.getLogger(__name__)

# TikTok Creative Center API endpoints (public, no auth required)
TIKTOK_TRENDING_URL = "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list"
TIKTOK_KEYWORD_URL = "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/keyword/list"


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_trending_hashtags(keyword: str, country: str = "US", period: int = 7):
    """Fetch trending hashtag data from TikTok Creative Center.

    The Creative Center API is public but may change without notice.
    Falls back gracefully if the API is unavailable.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en",
    }

    params = {
        "page": 1,
        "limit": 20,
        "period": period,  # 7 = last 7 days, 30 = last 30 days
        "country_code": country,
        "sort_by": "popular",
        "keyword": keyword,
    }

    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(TIKTOK_TRENDING_URL, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                logger.warning(f"TikTok API returned code {data.get('code')}: {data.get('msg')}")
                return []

            hashtags = []
            for item in data.get("data", {}).get("list", []):
                hashtags.append({
                    "hashtag": item.get("hashtag_name", ""),
                    "video_count": item.get("video_count", 0),
                    "view_count": item.get("publish_cnt", 0),
                })
            return hashtags

    except httpx.HTTPError as e:
        logger.error(f"TikTok API request failed: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching TikTok data: {e}")
        return []


def fetch_ad_count(keyword: str) -> int:
    """Estimate the number of active TikTok ads using a keyword.

    Uses TikTok Top Ads library (public).
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en",
    }

    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(
                "https://ads.tiktok.com/creative_radar_api/v1/top_ads/list",
                headers=headers,
                params={
                    "page": 1,
                    "limit": 1,
                    "period": 30,
                    "country_code": "US",
                    "keyword": keyword,
                    "order_by": "like",
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("pagination", {}).get("total_count", 0)
    except Exception as e:
        logger.warning(f"Failed to get ad count for '{keyword}': {e}")
        return 0


def collect_tiktok_trends():
    """Collect TikTok trend data for all watchlist keywords."""
    db = get_db()
    cursor = db.cursor()
    total_collected = 0
    today = datetime.utcnow().strftime("%Y-%m-%d")

    watchlist = get_active_keywords()

    for category, keywords in watchlist.items():
        for keyword in keywords:
            logger.info(f"Collecting TikTok trends for: {keyword}")

            try:
                TIKTOK.wait_if_needed()
            except RateLimitExceeded as e:
                logger.warning(f"Stopping TikTok collection: {e}")
                db.commit()
                db.close()
                return total_collected

            hashtags = fetch_trending_hashtags(keyword)
            TIKTOK.record_request()
            ad_count = fetch_ad_count(keyword)
            TIKTOK.record_request()

            total_views = sum(h.get("view_count", 0) for h in hashtags)
            total_videos = sum(h.get("video_count", 0) for h in hashtags)
            top_hashtag = hashtags[0]["hashtag"] if hashtags else ""

            try:
                cursor.execute(
                    """INSERT OR REPLACE INTO tiktok_trends
                       (keyword, hashtag, video_count, view_count, ad_count, date, collected_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        keyword,
                        top_hashtag,
                        total_videos,
                        total_views,
                        ad_count,
                        today,
                        datetime.utcnow().isoformat(),
                    ),
                )
                total_collected += 1
            except Exception as e:
                logger.error(f"Failed to store TikTok data for '{keyword}': {e}")

            # Rate limiting
            time.sleep(3)

    db.commit()
    db.close()
    logger.info(f"TikTok collection complete. {total_collected} keywords processed.")
    return total_collected


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if "--test" in sys.argv:
        logger.info("Running TikTok trends test...")
        results = fetch_trending_hashtags("nail stickers")
        for r in results[:5]:
            print(f"  #{r['hashtag']}: {r['video_count']} videos, {r['view_count']} views")
        ad_count = fetch_ad_count("nail stickers")
        print(f"  Active ads: {ad_count}")
        if results:
            print("Test passed.")
        else:
            print("No data returned. TikTok API may have changed.")
    else:
        collect_tiktok_trends()
