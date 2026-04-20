"""YouTube Data API v3 trend collector.

Replaces the dead TikTok Creative Center scraper. For each active keyword
(selected by the daily rotation policy), fetches the top 10 videos from
the last 30 days and writes a content_trends row summarizing view volume
and 7-day publish velocity.

Quota: search.list = 100 units, videos.list = 1 unit per 50 IDs.
Per keyword approx 101 units. Free tier is 10,000 units/day, so budget caps
at 99 keywords/day by default.
"""
import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import DB_PATH, YOUTUBE_API_KEY, YOUTUBE_DAILY_KEYWORD_BUDGET
from rate_limiter import YOUTUBE, RateLimitExceeded

logger = logging.getLogger(__name__)


def _select_keywords(budget: int) -> list:
    """Return (id, keyword) tuples up to `budget`, with weekly rotation.

    Policy (matches spec):
      - Top 80 keywords by most-recent niche score: every day.
      - Long-tail (rank 80 to 80+560=640): rotated across 7 days using
        today's weekday as an offset, so each long-tail keyword is covered
        once a week.
      - Budget caps the total returned.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        # All active keywords, ranked by most-recent category niche score.
        ranked = conn.execute(
            """
            SELECT k.id, k.keyword, k.category,
                   COALESCE(ns.overall_score, 0) AS score
            FROM keywords k
            LEFT JOIN (
                SELECT category, MAX(date) AS d FROM niche_scores GROUP BY category
            ) latest ON latest.category = k.category
            LEFT JOIN niche_scores ns
                ON ns.category = k.category AND ns.date = latest.d
            WHERE k.is_active = 1
            ORDER BY score DESC, k.added_at DESC
            """
        ).fetchall()
    finally:
        conn.close()

    top_n = min(80, budget, len(ranked))
    top = ranked[:top_n]

    longtail_pool = ranked[top_n:top_n + 560]
    weekday = datetime.now(timezone.utc).weekday()  # 0=Mon..6=Sun
    slot = len(longtail_pool) // 7 or 1
    start = (weekday * slot) % max(len(longtail_pool), 1)
    remaining = budget - len(top)
    longtail = longtail_pool[start:start + remaining] if remaining > 0 else []

    return [(r[0], r[1]) for r in (top + longtail)]


def fetch_trends(client, keyword: str) -> dict:
    """Fetch the top 10 recent videos for `keyword` and summarize them."""
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")

    search_resp = client.search().list(
        q=keyword,
        part="id",
        type="video",
        order="viewCount",
        publishedAfter=published_after,
        maxResults=10,
    ).execute()

    video_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
    if not video_ids:
        return {
            "video_count_7d": 0,
            "video_count_30d": 0,
            "total_views_30d": 0,
            "top_video_views": 0,
            "avg_views_per_video": 0,
            "raw": {"search": search_resp, "videos": None},
        }

    videos_resp = client.videos().list(
        id=",".join(video_ids),
        part="statistics,snippet",
    ).execute()

    items = videos_resp.get("items", [])
    views = [int(item["statistics"].get("viewCount", 0)) for item in items]
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    def _published(item):
        return datetime.fromisoformat(
            item["snippet"]["publishedAt"].replace("Z", "+00:00")
        )

    return {
        "video_count_7d": sum(1 for item in items if _published(item) >= seven_days_ago),
        "video_count_30d": len(items),
        "total_views_30d": sum(views),
        "top_video_views": max(views) if views else 0,
        "avg_views_per_video": sum(views) // len(views) if views else 0,
        "raw": {"search": search_resp, "videos": videos_resp},
    }


def collect_youtube_trends(budget_override=None):
    """Run the daily YouTube collection. Returns (success, items, error)."""
    if not YOUTUBE_API_KEY:
        return (False, 0, "YOUTUBE_API_KEY not set")

    budget = budget_override if budget_override is not None else YOUTUBE_DAILY_KEYWORD_BUDGET
    keywords = _select_keywords(budget)
    if not keywords:
        logger.warning("No active keywords found - skipping YouTube collection")
        return (True, 0, None)

    client = build("youtube", "v3", developerKey=YOUTUBE_API_KEY, cache_discovery=False)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    cursor = conn.cursor()
    total_written = 0
    collected_at = datetime.utcnow().isoformat(timespec="seconds")

    for kw_id, keyword in keywords:
        try:
            YOUTUBE.wait_if_needed()
        except RateLimitExceeded as e:
            logger.warning(f"YouTube daily limit reached: {e}")
            break

        try:
            signals = fetch_trends(client, keyword)
        except HttpError as e:
            logger.error(f"YouTube API error for '{keyword}': {e}")
            YOUTUBE.record_request()
            if e.resp.status in (403,) and "quotaExceeded" in str(e):
                logger.warning("Quota exceeded; stopping run.")
                break
            continue
        except Exception as e:
            logger.error(f"Unexpected error for '{keyword}': {e}", exc_info=True)
            YOUTUBE.record_request()
            continue

        YOUTUBE.record_request()

        cursor.execute(
            """INSERT INTO content_trends
                   (keyword_id, source, collected_at,
                    video_count_7d, video_count_30d,
                    total_views_30d, top_video_views,
                    avg_views_per_video, raw_json)
               VALUES (?, 'youtube', ?, ?, ?, ?, ?, ?, ?)""",
            (
                kw_id,
                collected_at,
                signals["video_count_7d"],
                signals["video_count_30d"],
                signals["total_views_30d"],
                signals["top_video_views"],
                signals["avg_views_per_video"],
                json.dumps(signals["raw"])[:100_000],  # cap blob size
            ),
        )
        total_written += 1
        conn.commit()  # commit per row so partial runs aren't lost

    conn.close()
    logger.info(f"YouTube collection complete: {total_written} keywords written")
    return (True, total_written, None)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success, items, err = collect_youtube_trends()
    print(f"success={success} items={items} err={err}")
