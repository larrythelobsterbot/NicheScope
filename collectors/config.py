"""NicheScope configuration: DB-driven watchlists, API keys, thresholds, dynamic colors."""

import os
import sqlite3
from contextlib import contextmanager

# API Keys (load from environment variables in production)
KEEPA_API_KEY = os.getenv("KEEPA_API_KEY", "")
AMAZON_ACCESS_KEY = os.getenv("AMAZON_ACCESS_KEY", "")
AMAZON_SECRET_KEY = os.getenv("AMAZON_SECRET_KEY", "")
AMAZON_PARTNER_TAG = os.getenv("AMAZON_PARTNER_TAG", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ALIBABA_APP_KEY = os.getenv("ALIBABA_APP_KEY", "")
ALIBABA_APP_SECRET = os.getenv("ALIBABA_APP_SECRET", "")

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "nichescope.db"),
)

# ============================================================
# CRITICAL: All watchlists are DATABASE-DRIVEN, not hardcoded.
# The seed script populates initial data. After that, users
# add/remove keywords, ASINs, competitors, and suppliers
# through the dashboard admin UI or the Telegram bot.
# ============================================================


@contextmanager
def get_db():
    """Get a database connection with WAL mode and busy timeout for concurrency."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def get_active_keywords():
    """Pull all active keywords from the database, grouped by category."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    rows = conn.execute(
        "SELECT keyword, category FROM keywords WHERE is_active = 1"
    ).fetchall()
    conn.close()
    watchlist = {}
    for keyword, category in rows:
        watchlist.setdefault(category, []).append(keyword)
    return watchlist


def get_tracked_asins():
    """Pull all active ASINs from the database, grouped by category."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    rows = conn.execute(
        "SELECT asin, category FROM products WHERE is_active = 1"
    ).fetchall()
    conn.close()
    asins = {}
    for asin, category in rows:
        asins.setdefault(category, []).append(asin)
    return asins


def get_competitors():
    """Pull all competitor domains from the database."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    rows = conn.execute(
        "SELECT name, domain, category FROM competitors"
    ).fetchall()
    conn.close()
    comps = {}
    for name, domain, category in rows:
        comps.setdefault(category, []).append({"name": name, "domain": domain})
    return comps


def get_categories():
    """Get all unique categories currently being tracked."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    rows = conn.execute(
        "SELECT DISTINCT category FROM keywords WHERE is_active = 1 ORDER BY category"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


# Scoring weights (these stay in config, not DB)
SCORE_WEIGHTS = {
    "trend": 0.25,
    "margin": 0.20,
    "competition": 0.15,
    "sourcing": 0.15,
    "content": 0.10,
    "repeat_purchase": 0.15,
}

# Alert thresholds
ALERT_THRESHOLDS = {
    "trend_spike_pct": 30,
    "price_drop_pct": 15,
    "new_competitor_traffic": 50000,
}

# Dynamic color palette for categories.
CATEGORY_PALETTE = [
    "#FF6B8A",  # pink (beauty default)
    "#A78BFA",  # purple (jewelry default)
    "#34D399",  # green (travel default)
    "#FBBF24",  # amber
    "#60A5FA",  # blue
    "#FB923C",  # orange
    "#F472B6",  # hot pink
    "#2DD4BF",  # teal
    "#C084FC",  # violet
    "#4ADE80",  # lime
    "#E879F9",  # fuchsia
    "#38BDF8",  # sky
    "#A3E635",  # yellow-green
    "#F97316",  # deep orange
    "#818CF8",  # indigo
]


def get_category_color(category: str) -> str:
    """Assign a consistent color to any category based on its position in the DB."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        row = conn.execute(
            "SELECT color_override FROM categories WHERE name = ? AND color_override IS NOT NULL",
            (category,),
        ).fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
    except Exception:
        pass

    categories = get_categories()
    if category in categories:
        idx = categories.index(category)
    else:
        idx = hash(category) % len(CATEGORY_PALETTE)
    return CATEGORY_PALETTE[idx % len(CATEGORY_PALETTE)]


def get_all_category_colors() -> dict:
    """Get color assignments for all active categories."""
    categories = get_categories()
    colors = {}
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        overrides = dict(
            conn.execute(
                "SELECT name, color_override FROM categories WHERE color_override IS NOT NULL"
            ).fetchall()
        )
        conn.close()
    except Exception:
        overrides = {}

    for i, cat in enumerate(categories):
        if cat in overrides and overrides[cat]:
            colors[cat] = overrides[cat]
        else:
            colors[cat] = CATEGORY_PALETTE[i % len(CATEGORY_PALETTE)]
    return colors


# Collection schedule (HKT = UTC+8)
SCHEDULE = {
    "google_trends": {"hour": 6, "minute": 0},
    "keepa": {"hours": 6},
    "tiktok": {"hour": 8, "minute": 0},
    "alibaba": {"day_of_week": "mon", "hour": 2},
    "daily_digest": {"hour": 9, "minute": 0},
    "weekly_analysis": {"day_of_week": "sun", "hour": 0},
}
