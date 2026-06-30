"""NicheScope configuration: DB-driven watchlists, API keys, thresholds, dynamic colors."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

# API Keys (load from environment variables in production)
KEEPA_API_KEY = os.getenv("KEEPA_API_KEY", "")
AMAZON_ACCESS_KEY = os.getenv("AMAZON_ACCESS_KEY", "")
AMAZON_SECRET_KEY = os.getenv("AMAZON_SECRET_KEY", "")
AMAZON_PARTNER_TAG = os.getenv("AMAZON_PARTNER_TAG", "")
# Amazon Creators API (PA-API's successor) — OAuth2-style credentials from
# Associates Central -> Tools -> Creators API -> Add new credential
AMAZON_CREATORS_CREDENTIAL_ID = os.getenv("AMAZON_CREATORS_CREDENTIAL_ID", "")
AMAZON_CREATORS_CREDENTIAL_SECRET = os.getenv("AMAZON_CREATORS_CREDENTIAL_SECRET", "")
AMAZON_CREATORS_VERSION = os.getenv("AMAZON_CREATORS_VERSION", "v3.1")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ALIBABA_APP_KEY = os.getenv("ALIBABA_APP_KEY", "")
ALIBABA_APP_SECRET = os.getenv("ALIBABA_APP_SECRET", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_DAILY_KEYWORD_BUDGET = int(os.getenv("YOUTUBE_DAILY_KEYWORD_BUDGET", "99"))

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


# Lifecycle-weighted collection: how many days between Google Trends refreshes
# for a keyword, by its lifecycle stage (from keyword_metrics). Rising keywords
# stay fresh; dead weight is checked rarely. A flat rotation spent the whole
# rate-limit budget refreshing keywords nobody searches; this targets it.
COLLECTION_CADENCE = {
    "emerging": 1,       # daily — the keywords we most want to catch moving
    "accelerating": 1,   # daily
    "peaking": 7,        # weekly — at the top, watch for the turn
    "stable": 7,         # weekly
    "declining": 30,     # monthly — confirm it's still dead, cheaply
}
COLLECTION_CADENCE_DEFAULT = 1  # no metrics yet (new keyword) -> collect to seed a baseline

# Priority rank for partial (rate-limited) runs: lower = collected first, so
# when the daily budget runs out the most important keywords are already done.
_LIFECYCLE_RANK = {
    "emerging": 0, "accelerating": 0,
    "peaking": 1, "stable": 1,
    "declining": 2,
}


def get_keywords_due_for_collection():
    """Active keywords due for a Google Trends refresh today, in priority order.

    Returns a flat list of (keyword, category) tuples. "Due" means the keyword
    has not been collected within its lifecycle cadence (or never has). The list
    is ordered so a rate-limited partial run covers rising, high-interest
    keywords before stale ones — and interleaves categories implicitly because
    the sort key is lifecycle+interest, not category.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT k.keyword, k.category, km.lifecycle AS lifecycle,
                      COALESCE(km.current_interest, 0) AS interest,
                      (SELECT MAX(collected_at) FROM trend_data
                       WHERE keyword_id = k.id) AS last_collected
               FROM keywords k
               LEFT JOIN keyword_metrics km ON km.keyword_id = k.id
               WHERE k.is_active = 1"""
        ).fetchall()
    except sqlite3.OperationalError:
        # keyword_metrics missing (pre-migration) — fall back to all active
        conn.close()
        return [(kw, cat) for cat, kws in get_active_keywords().items() for kw in kws]
    conn.close()

    now = datetime.utcnow()
    due = []
    for r in rows:
        cadence = COLLECTION_CADENCE.get(r["lifecycle"], COLLECTION_CADENCE_DEFAULT)
        last = r["last_collected"]
        is_due = True
        if last:
            try:
                if (now - datetime.fromisoformat(last)).days < cadence:
                    is_due = False
            except (ValueError, TypeError):
                is_due = True
        if is_due:
            due.append(r)

    due.sort(key=lambda r: (_LIFECYCLE_RANK.get(r["lifecycle"], 0), -r["interest"]))
    return [(r["keyword"], r["category"]) for r in due]


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
    # Minimum current interest for a velocity spike to count as a breakout;
    # below this, percent changes are noise (interest 2 -> 3 is "+50%").
    "min_interest": 10,
    # Suppress duplicate alerts for the same subject within this window.
    "alert_dedup_days": 7,
    # Auto-acknowledge unread alerts older than this.
    "alert_expiry_days": 30,
}

# Keepa product bootstrap: top keywords per category get their best-selling
# ASINs auto-discovered via product_finder and inserted into `products`.
KEEPA_BOOTSTRAP = {
    "keywords_per_category": 3,
    "asins_per_keyword": 5,
}

# Discovery rebalancing: related-query expansion samples at most this many
# parent keywords per category per run. Without a cap the dominant category
# (beauty, 67% of keywords) consumes the whole Google Trends budget and
# discovers only more of itself.
DISCOVERY = {
    "parents_per_category": 25,
}

# Pending-keyword auto-triage thresholds
TRIAGE = {
    "auto_reject_relevance": 0.3,   # below this -> auto-reject
    "auto_approve_relevance": 0.6,  # at/above this (and not junk) -> auto-approve
    "stale_days": 30,               # pending longer than this -> auto-reject
    "max_auto_approvals_per_category": 10,  # per run
    # Categories already holding more than this share of active keywords get
    # no auto-approvals (manual review only) so imbalance stops compounding.
    "max_category_share": 0.4,
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
    "keepa_bootstrap": {"day_of_week": "mon", "hour": 1},
    "amazon_pa": {"hour": 7, "minute": 0},
    "tiktok": {"hour": 8, "minute": 0},
    "youtube": {"hour": 8, "minute": 0},
    "alibaba": {"day_of_week": "mon", "hour": 2},
    "daily_digest": {"hour": 9, "minute": 0},
    "weekly_analysis": {"day_of_week": "sun", "hour": 0},
    "prune": {"day_of_week": "sun", "hour": 1},
}

# Dead-keyword pruning thresholds (used by collectors/pruner.py).
PRUNE = {
    "max_peak": 5,        # peak interest over the window below
    "window_days": 84,    # ~12 weeks
    "min_age_days": 90,   # don't judge keywords younger than this
    "min_points": 8,      # require enough data points to trust the verdict
}
