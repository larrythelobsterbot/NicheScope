"""
Centralized rate limiter for all NicheScope collectors.
Tracks quotas per service and enforces delays between requests.
"""
import time
import sqlite3
from datetime import datetime
from config import DB_PATH


class RateLimiter:
    """Token bucket rate limiter with persistent state."""

    def __init__(self, service_name, requests_per_minute, daily_limit=None):
        self.service = service_name
        self.rpm = requests_per_minute
        self.daily_limit = daily_limit
        self.min_interval = 60.0 / requests_per_minute
        self.last_request = 0
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limits (
                service TEXT NOT NULL,
                date DATE NOT NULL,
                request_count INTEGER DEFAULT 0,
                last_request_at DATETIME,
                UNIQUE(service, date)
            )
        """)
        conn.commit()
        conn.close()

    def wait_if_needed(self):
        """Block until it is safe to make the next request."""
        # Enforce minimum interval
        elapsed = time.time() - self.last_request
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            time.sleep(sleep_time)

        # Check daily limit
        if self.daily_limit:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            today = datetime.now().strftime("%Y-%m-%d")
            row = conn.execute(
                "SELECT request_count FROM rate_limits WHERE service = ? AND date = ?",
                (self.service, today)
            ).fetchone()

            if row and row[0] >= self.daily_limit:
                conn.close()
                raise RateLimitExceeded(
                    f"{self.service}: Daily limit of {self.daily_limit} reached. "
                    f"Resuming tomorrow."
                )
            conn.close()

        self.last_request = time.time()

    def record_request(self):
        """Record that a request was made."""
        conn = sqlite3.connect(DB_PATH, timeout=30)
        today = datetime.now().strftime("%Y-%m-%d")
        conn.execute("""
            INSERT INTO rate_limits (service, date, request_count, last_request_at)
            VALUES (?, ?, 1, datetime('now'))
            ON CONFLICT(service, date) DO UPDATE SET
                request_count = request_count + 1,
                last_request_at = datetime('now')
        """, (self.service, today))
        conn.commit()
        conn.close()

    def get_remaining_today(self):
        """How many requests are left today."""
        if not self.daily_limit:
            return float('inf')
        conn = sqlite3.connect(DB_PATH, timeout=30)
        today = datetime.now().strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT request_count FROM rate_limits WHERE service = ? AND date = ?",
            (self.service, today)
        ).fetchone()
        conn.close()
        used = row[0] if row else 0
        return max(0, self.daily_limit - used)

    def get_used_today(self):
        """How many requests have been made today."""
        conn = sqlite3.connect(DB_PATH, timeout=30)
        today = datetime.now().strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT request_count, last_request_at FROM rate_limits WHERE service = ? AND date = ?",
            (self.service, today)
        ).fetchone()
        conn.close()
        if row:
            return {"count": row[0], "last_request_at": row[1]}
        return {"count": 0, "last_request_at": None}


class RateLimitExceeded(Exception):
    pass


# Pre-configured limiters for each service
GOOGLE_TRENDS = RateLimiter(
    service_name="google_trends",
    requests_per_minute=1,       # 1 req/min to avoid blocks
    daily_limit=1400             # Google's approximate daily threshold
)

KEEPA_API = RateLimiter(
    service_name="keepa",
    requests_per_minute=25,      # 50 tokens/min on cheapest tier, ~2 tokens per request
    daily_limit=None             # Token-based, not daily-limited
)

AMAZON_PA = RateLimiter(
    service_name="amazon_pa",
    requests_per_minute=1,       # New associates: 1 req/sec but be conservative
    daily_limit=8640             # PA-API daily limit for new associates
)

ALIBABA_SCRAPE = RateLimiter(
    service_name="alibaba",
    requests_per_minute=0.5,     # 1 request per 2 minutes, very conservative
    daily_limit=100              # Do not hammer Alibaba
)

TIKTOK = RateLimiter(
    service_name="tiktok",
    requests_per_minute=2,
    daily_limit=500
)

SIMILARWEB = RateLimiter(
    service_name="similarweb",
    requests_per_minute=1,
    daily_limit=50               # Free tier is very limited
)

# YouTube Data API v3: 10,000 quota units/day free tier.
# search.list = 100 units; videos.list = 1 unit per 50 IDs.
# At ~101 units/keyword, daily cap is 99 keywords. Use the budget in config.py.
YOUTUBE = RateLimiter(
    service_name="youtube",
    requests_per_minute=100,  # API hard limit is far higher; keep friendly
    daily_limit=200,  # 99 keywords × 2 calls each = 198 requests
)
