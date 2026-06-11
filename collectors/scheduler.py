"""
APScheduler orchestrator for all NicheScope data collection jobs.
Production-ready: loads .env, logs everything, tracks collector health,
alerts on repeated failures via Telegram. Never crashes.
"""

import json
import logging
import os
import signal
import sqlite3
import sys
from datetime import datetime

from dotenv import load_dotenv


def load_env_or_die(env_path):
    """Load .env and abort loudly if it's missing.

    Previously this was silent; a missing .env disabled conditional collectors
    (like Keepa) at scheduler startup with no error visible in the logs.
    """
    if not os.path.exists(env_path):
        print(
            f"ERROR: .env file not found at {env_path}. "
            "Scheduler cannot start without it.",
            file=sys.stderr,
        )
        sys.exit(1)
    load_dotenv(env_path)


# Load .env from parent directory (for VPS deployment)
_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
if __name__ == "__main__" or os.environ.get("NICHESCOPE_REQUIRE_ENV") == "1":
    load_env_or_die(_ENV_PATH)
else:
    # During tests, importing scheduler should NOT terminate the interpreter.
    # Callers must invoke load_env_or_die explicitly.
    if os.path.exists(_ENV_PATH):
        load_dotenv(_ENV_PATH)

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from config import DB_PATH, SCHEDULE, get_active_keywords
from google_trends import collect_trends
from keepa_collector import collect_products, detect_anomalies, bootstrap_products
from tiktok_trends import collect_tiktok_trends
from youtube_trends import collect_youtube_trends
from alibaba_collector import collect_alibaba_suppliers
from similarweb import collect_competitor_traffic
from analyzer import run_analysis, detect_breakouts, generate_alerts
from discovery import run_discovery
from reddit_discovery import discover_from_reddit
from etsy_discovery import discover_from_etsy
from amazon_bestsellers import collect_amazon_bestsellers
from pending_triage import triage_pending
from telegram_bot import (
    send_daily_digest,
    send_discovery_digest,
    send_breakout_alert,
    send_price_alert,
    send_telegram,
    poll_for_commands,
)

# Configure logging with both console and file output
log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(log_dir, "scheduler.log")),
    ],
)

logger = logging.getLogger("nichescope")


# ============================================================
# Collector Health Tracking
# ============================================================

def get_health_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def run_collector_job(name: str, fn):
    """Invoke a collector function, normalize its return, and record real health.

    Accepts collectors that return either:
      - (success: bool, items_written: int, error: str | None)
      - int (legacy — treated as success with that row count)
      - None (legacy — treated as success with 0 row count)

    Never raises. Returns the normalized tuple.
    """
    try:
        result = fn()
    except Exception as e:
        logger.error(f"[{name}] collector raised: {e}", exc_info=True)
        _write_health(name, success=False, items=0, error=str(e)[:500])
        return (False, 0, str(e))

    if isinstance(result, tuple) and len(result) == 3:
        success, items, error = result
    elif isinstance(result, int):
        success, items, error = True, result, None
    elif result is None:
        success, items, error = True, 0, None
    else:
        logger.warning(f"[{name}] returned unexpected type {type(result).__name__}; treating as success")
        success, items, error = True, 0, None

    _write_health(name, success=success, items=items, error=error)
    _check_stall(name)
    return (success, items, error)


def _write_health(name: str, success: bool, items: int, error):
    """Low-level health writer with row-count + status."""
    try:
        db = get_health_db()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        status = "success" if success else "failed"
        if success:
            db.execute(
                """INSERT INTO collector_health
                       (collector_name, last_run, last_success, last_error,
                        consecutive_failures, total_runs, total_successes,
                        items_collected, last_status, updated_at)
                   VALUES (?, ?, ?, NULL, 0, 1, 1, ?, ?, ?)
                   ON CONFLICT(collector_name) DO UPDATE SET
                       last_run = excluded.last_run,
                       last_success = excluded.last_success,
                       last_error = NULL,
                       consecutive_failures = 0,
                       total_runs = total_runs + 1,
                       total_successes = total_successes + 1,
                       items_collected = excluded.items_collected,
                       last_status = excluded.last_status,
                       updated_at = excluded.updated_at""",
                (name, now, now, items, status, now),
            )
        else:
            err = (error or "Unknown")[:500]
            db.execute(
                """INSERT INTO collector_health
                       (collector_name, last_run, last_error, consecutive_failures,
                        total_runs, total_successes, items_collected, last_status, updated_at)
                   VALUES (?, ?, ?, 1, 1, 0, ?, ?, ?)
                   ON CONFLICT(collector_name) DO UPDATE SET
                       last_run = excluded.last_run,
                       last_error = excluded.last_error,
                       consecutive_failures = consecutive_failures + 1,
                       total_runs = total_runs + 1,
                       items_collected = excluded.items_collected,
                       last_status = excluded.last_status,
                       updated_at = excluded.updated_at""",
                (name, now, err, items, status, now),
            )

        # Stall tracking: count successful runs that wrote zero rows with no
        # skip reason. A collector that "succeeds" with 0 items for many runs
        # is silently broken (e.g. Keepa with an unseeded products table).
        try:
            if success and items > 0:
                db.execute(
                    "UPDATE collector_health SET consecutive_zero_runs = 0 WHERE collector_name = ?",
                    (name,),
                )
            elif success and items == 0 and error is None:
                db.execute(
                    "UPDATE collector_health SET consecutive_zero_runs = consecutive_zero_runs + 1 "
                    "WHERE collector_name = ?",
                    (name,),
                )
        except sqlite3.OperationalError:
            logger.warning("collector_health.consecutive_zero_runs missing — run scripts/migrate_003_stall_guard.py")

        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"[{name}] failed to record health: {e}")


STALL_THRESHOLD = 5  # consecutive zero-row "successes" before alerting


def _check_stall(collector_name):
    """Alert when a collector keeps reporting success but writes nothing."""
    try:
        db = get_health_db()
        try:
            row = db.execute(
                "SELECT consecutive_zero_runs FROM collector_health WHERE collector_name = ?",
                (collector_name,),
            ).fetchone()
        except sqlite3.OperationalError:
            db.close()
            return

        if not row or (row["consecutive_zero_runs"] or 0) < STALL_THRESHOLD:
            db.close()
            return

        zero_runs = row["consecutive_zero_runs"]

        # Dedup: one stall alert per collector per 7 days
        existing = db.execute(
            """SELECT 1 FROM alerts
               WHERE type = 'collector_stalled'
                 AND json_extract(data, '$.collector') = ?
                 AND sent_at >= datetime('now', '-7 days')
               LIMIT 1""",
            (collector_name,),
        ).fetchone()
        if existing:
            db.close()
            return

        message = (
            f"Collector '{collector_name}' reported success but wrote 0 rows "
            f"for {zero_runs} consecutive runs — likely silently broken."
        )
        db.execute(
            "INSERT INTO alerts (type, severity, message, data) VALUES (?, ?, ?, ?)",
            (
                "collector_stalled",
                "warning",
                message,
                json.dumps({"collector": collector_name, "zero_runs": zero_runs}),
            ),
        )
        db.commit()
        db.close()

        logger.warning(message)
        send_telegram(f"<b>Collector Stalled</b>\n\n{message}")
    except Exception as e:
        logger.error(f"Stall check failed for {collector_name}: {e}")


def check_and_alert_failures(collector_name):
    """Send Telegram alert if a collector has failed 3+ times in a row."""
    try:
        db = get_health_db()
        row = db.execute(
            "SELECT consecutive_failures, last_error FROM collector_health WHERE collector_name = ?",
            (collector_name,)
        ).fetchone()
        db.close()

        if row and row["consecutive_failures"] >= 3:
            failures = row["consecutive_failures"]
            error = row["last_error"] or "Unknown"
            message = (
                f"<b>Collector Alert</b>\n\n"
                f"<b>{collector_name}</b> has failed {failures} times in a row.\n"
                f"Last error: <code>{error[:200]}</code>\n\n"
                f"Check logs: <code>pm2 logs nichescope-collectors --lines 50</code>"
            )
            send_telegram(message)
            logger.warning(
                f"Alert sent: {collector_name} failed {failures} consecutive times"
            )
    except Exception as e:
        logger.error(f"Failed to check/alert for {collector_name}: {e}")


# ============================================================
# Job Listener (tracks all job outcomes)
# ============================================================

def job_listener(event):
    """Escalate repeated consecutive failures to Telegram."""
    job_id = event.job_id
    if event.exception:
        logger.error(f"Job '{job_id}' raised past run_collector_job — unexpected")
        check_and_alert_failures(job_id)


# ============================================================
# Job Wrappers (each catches its own exceptions)
# ============================================================

def job_google_trends():
    logger.info("=== Google Trends collection started ===")
    success, count, err = run_collector_job("google_trends", collect_trends)
    if success:
        run_post_collection()
    return (success, count, err)


def job_keepa_bootstrap():
    logger.info("=== Keepa product bootstrap started ===")
    if not os.getenv("KEEPA_API_KEY"):
        logger.warning("KEEPA_API_KEY not set; skipping bootstrap.")
        return (True, 0, "KEEPA_API_KEY not set")
    return run_collector_job("keepa_bootstrap", bootstrap_products)


def job_keepa():
    logger.info("=== Keepa collection started ===")
    if not os.getenv("KEEPA_API_KEY"):
        logger.warning("KEEPA_API_KEY not set; skipping this run.")
        return (True, 0, "KEEPA_API_KEY not set")

    # Self-heal: if no ASINs are tracked yet, bootstrap from the keyword
    # watchlist instead of "succeeding" with zero rows forever.
    try:
        db = get_health_db()
        product_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM products WHERE is_active = 1"
        ).fetchone()["cnt"]
        db.close()
        if product_count == 0:
            logger.warning("products table is empty — running bootstrap before collection.")
            job_keepa_bootstrap()
    except Exception as e:
        logger.error(f"Pre-Keepa product check failed: {e}")

    success, count, err = run_collector_job("keepa", collect_products)
    if success and count > 0:
        try:
            anomalies = detect_anomalies()
            # Store with dedup; only telegram anomalies not already alerted
            new = generate_alerts([], anomalies)
            for anomaly in new["new_price_alerts"]:
                send_price_alert(anomaly)
        except Exception as e:
            logger.error(f"Post-Keepa analysis failed: {e}")
        run_post_collection()
    return (success, count, err)


def job_tiktok():
    logger.info("=== TikTok collection skipped (deprecated, see YouTube collector) ===")
    return (True, 0, "deprecated")


def job_youtube():
    logger.info("=== YouTube collection started ===")
    if not os.getenv("YOUTUBE_API_KEY"):
        logger.warning("YOUTUBE_API_KEY not set; skipping this run.")
        return (True, 0, "YOUTUBE_API_KEY not set")
    success, count, err = run_collector_job("youtube", collect_youtube_trends)
    if success and count > 0:
        run_post_collection()
    return (success, count, err)


def job_alibaba():
    logger.info("=== Alibaba supplier scan started ===")
    return run_collector_job("alibaba", collect_alibaba_suppliers)


def job_competitor_traffic():
    logger.info("=== Competitor traffic collection started ===")
    return run_collector_job("competitor_traffic", collect_competitor_traffic)


def job_daily_digest():
    logger.info("=== Daily digest job started ===")
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        logger.info("TELEGRAM_BOT_TOKEN not set; skipping digest.")
        return (True, 0, None)
    try:
        send_daily_digest()
        return (True, 1, None)
    except Exception as e:
        logger.error(f"Daily digest failed: {e}", exc_info=True)
        return (False, 0, str(e))


def job_weekly_analysis():
    logger.info("=== Weekly deep analysis started ===")
    def _wrapped():
        results = run_analysis()
        for b in results.get("breakouts", []):
            if b["severity"] == "critical" and b.get("is_new"):
                send_breakout_alert(b)
        return (True, len(results.get("breakouts", [])), None)
    return run_collector_job("weekly_analysis", _wrapped)


def job_telegram_poll():
    """Poll Telegram for incoming commands."""
    try:
        poll_for_commands()
    except Exception as e:
        logger.error(f"Telegram poll failed: {e}")


def job_discovery_categories():
    logger.info("=== Discovery: category scan started ===")
    success, count, err = run_collector_job("discovery_categories", run_discovery)
    if success:
        try:
            send_discovery_digest()
        except Exception as e:
            logger.error(f"Discovery digest failed: {e}")
    return (success, count, err)


def job_discovery_related():
    logger.info("=== Discovery: related queries scan started ===")
    def _wrapped():
        from discovery import discover_from_related_queries
        return discover_from_related_queries()
    success, count, err = run_collector_job("discovery_related", _wrapped)
    if success:
        try:
            send_discovery_digest()
        except Exception as e:
            logger.error(f"Discovery digest failed: {e}")
    return (success, count, err)


def job_reddit_discovery():
    logger.info("=== Reddit discovery started ===")
    success, count, err = run_collector_job("reddit_discovery", discover_from_reddit)
    if success:
        try:
            send_discovery_digest()
        except Exception as e:
            logger.error(f"Discovery digest failed: {e}")
    return (success, count, err)


def job_etsy_discovery():
    logger.info("=== Etsy discovery started ===")
    success, count, err = run_collector_job("etsy_discovery", discover_from_etsy)
    if success:
        try:
            send_discovery_digest()
        except Exception as e:
            logger.error(f"Discovery digest failed: {e}")
    return (success, count, err)


def job_amazon_bestsellers():
    logger.info("=== Amazon Best Sellers discovery started ===")
    success, count, err = run_collector_job("amazon_bestsellers", collect_amazon_bestsellers)
    if success:
        try:
            send_discovery_digest()
        except Exception as e:
            logger.error(f"Discovery digest failed: {e}")
    return (success, count, err)


def job_pending_triage():
    logger.info("=== Pending keyword triage started ===")
    return run_collector_job("pending_triage", triage_pending)


def run_post_collection():
    """Run analysis after a collector finishes."""
    try:
        results = run_analysis()
        for b in results.get("breakouts", []):
            # is_new is set by generate_alerts; without it a persistent riser
            # would re-telegram after every collector run.
            if b["severity"] == "critical" and b.get("is_new"):
                send_breakout_alert(b)
    except Exception as e:
        logger.error(f"Post-collection analysis failed: {e}")


# ============================================================
# Initial Collection (on first deploy when DB is empty)
# ============================================================

def run_initial_collection_if_needed():
    """If the trend_data table is empty, kick off Google Trends immediately."""
    try:
        db = get_health_db()
        row = db.execute("SELECT COUNT(*) as cnt FROM trend_data").fetchone()
        db.close()

        if row["cnt"] == 0:
            logger.info("Database is empty. Running initial Google Trends collection now...")
            job_google_trends()
            logger.info("Initial collection complete.")
        else:
            logger.info(f"Database has {row['cnt']} trend data points. Skipping initial collection.")
    except Exception as e:
        logger.error(f"Initial collection check failed: {e}", exc_info=True)


# ============================================================
# Main Scheduler
# ============================================================

def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone="Asia/Hong_Kong")

    # Register the job listener for health tracking
    scheduler.add_listener(job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)

    # Google Trends: daily at 6am HKT
    scheduler.add_job(
        job_google_trends,
        CronTrigger(
            hour=SCHEDULE["google_trends"]["hour"],
            minute=SCHEDULE["google_trends"]["minute"],
            timezone="Asia/Hong_Kong",
        ),
        id="google_trends",
        name="Google Trends Collector",
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Keepa: every 6 hours (registered unconditionally; env checked at runtime)
    scheduler.add_job(
        job_keepa,
        IntervalTrigger(hours=SCHEDULE["keepa"]["hours"]),
        id="keepa",
        name="Keepa Product Collector",
        misfire_grace_time=1800,
        coalesce=True,
    )

    # Keepa bootstrap: weekly on Mondays at 1am HKT (refreshes tracked ASINs
    # to follow the keyword watchlist)
    scheduler.add_job(
        job_keepa_bootstrap,
        CronTrigger(
            day_of_week=SCHEDULE["keepa_bootstrap"]["day_of_week"],
            hour=SCHEDULE["keepa_bootstrap"]["hour"],
            timezone="Asia/Hong_Kong",
        ),
        id="keepa_bootstrap",
        name="Keepa Product Bootstrap",
        misfire_grace_time=7200,
        coalesce=True,
    )

    # TikTok: daily at 8am HKT
    scheduler.add_job(
        job_tiktok,
        CronTrigger(
            hour=SCHEDULE["tiktok"]["hour"],
            minute=SCHEDULE["tiktok"]["minute"],
            timezone="Asia/Hong_Kong",
        ),
        id="tiktok",
        name="TikTok Trends Collector",
        misfire_grace_time=3600,
        coalesce=True,
    )

    scheduler.add_job(
        job_youtube,
        CronTrigger(
            hour=SCHEDULE["youtube"]["hour"],
            minute=SCHEDULE["youtube"]["minute"],
            timezone="Asia/Hong_Kong",
        ),
        id="youtube",
        name="YouTube Trends Collector",
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Alibaba: weekly on Mondays at 2am HKT
    scheduler.add_job(
        job_alibaba,
        CronTrigger(
            day_of_week=SCHEDULE["alibaba"]["day_of_week"],
            hour=SCHEDULE["alibaba"]["hour"],
            timezone="Asia/Hong_Kong",
        ),
        id="alibaba",
        name="Alibaba Supplier Scanner",
        misfire_grace_time=7200,
        coalesce=True,
    )

    # Competitor traffic: weekly on Wednesday at 3am HKT
    scheduler.add_job(
        job_competitor_traffic,
        CronTrigger(day_of_week="wed", hour=3, timezone="Asia/Hong_Kong"),
        id="competitor_traffic",
        name="Competitor Traffic Estimator",
        misfire_grace_time=7200,
        coalesce=True,
    )

    # Discovery: category scan daily at 3am HKT
    scheduler.add_job(
        job_discovery_categories,
        CronTrigger(hour=3, minute=0, timezone="Asia/Hong_Kong"),
        id="discovery_categories",
        name="Discovery Category Scan",
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Discovery: related queries Wed + Sun at 3:30am HKT
    scheduler.add_job(
        job_discovery_related,
        CronTrigger(day_of_week="wed,sun", hour=3, minute=30, timezone="Asia/Hong_Kong"),
        id="discovery_related",
        name="Discovery Related Queries",
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Reddit discovery: Tue + Fri at 4:00am HKT
    scheduler.add_job(
        job_reddit_discovery,
        CronTrigger(day_of_week="tue,fri", hour=4, minute=0, timezone="Asia/Hong_Kong"),
        id="reddit_discovery",
        name="Reddit Discovery",
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Etsy discovery: Mon + Thu at 4:30am HKT
    scheduler.add_job(
        job_etsy_discovery,
        CronTrigger(day_of_week="mon,thu", hour=4, minute=30, timezone="Asia/Hong_Kong"),
        id="etsy_discovery",
        name="Etsy Discovery",
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Amazon Best Sellers: daily at 5am HKT
    scheduler.add_job(
        job_amazon_bestsellers,
        CronTrigger(hour=5, minute=0, timezone="Asia/Hong_Kong"),
        id="amazon_bestsellers",
        name="Amazon Best Sellers Discovery",
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Pending keyword triage: daily at 5:30am HKT (after the discovery jobs)
    scheduler.add_job(
        job_pending_triage,
        CronTrigger(hour=5, minute=30, timezone="Asia/Hong_Kong"),
        id="pending_triage",
        name="Pending Keyword Triage",
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Daily Telegram digest: 9am HKT (registered unconditionally; env checked at runtime)
    scheduler.add_job(
        job_daily_digest,
        CronTrigger(
            hour=SCHEDULE["daily_digest"]["hour"],
            minute=SCHEDULE["daily_digest"]["minute"],
            timezone="Asia/Hong_Kong",
        ),
        id="daily_digest",
        name="Daily Telegram Digest",
        misfire_grace_time=600,
        coalesce=True,
    )

    # Telegram command polling: every 30 seconds (still startup-gated since it
    # is not a collector job and only makes sense when a token is configured)
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        scheduler.add_job(
            job_telegram_poll,
            IntervalTrigger(seconds=30),
            id="telegram_poll",
            name="Telegram Command Poller",
        )
    else:
        logger.info("TELEGRAM_BOT_TOKEN not set. Telegram command polling disabled.")

    # Weekly deep analysis: Sunday midnight HKT
    scheduler.add_job(
        job_weekly_analysis,
        CronTrigger(
            day_of_week=SCHEDULE["weekly_analysis"]["day_of_week"],
            hour=SCHEDULE["weekly_analysis"]["hour"],
            timezone="Asia/Hong_Kong",
        ),
        id="weekly_analysis",
        name="Weekly Deep Analysis",
        misfire_grace_time=7200,
        coalesce=True,
    )

    # Run initial collection on first startup (only if DB is empty)
    scheduler.add_job(
        run_initial_collection_if_needed,
        "date",
        id="initial_collection",
        name="Initial Collection Check",
    )

    return scheduler


def main():
    load_env_or_die(_ENV_PATH)
    scheduler = build_scheduler()
    run_initial_collection_if_needed()
    signal.signal(signal.SIGINT, lambda *_: scheduler.shutdown())
    signal.signal(signal.SIGTERM, lambda *_: scheduler.shutdown())

    # Startup info
    keywords = get_active_keywords()
    total_kw = sum(len(v) for v in keywords.values())
    logger.info("=" * 60)
    logger.info("NicheScope scheduler started")
    logger.info(f"Tracking {total_kw} keywords across {len(keywords)} categories")
    logger.info(f"DB path: {DB_PATH}")
    logger.info(f"Scheduled jobs: {len(scheduler.get_jobs())}")
    for job in scheduler.get_jobs():
        next_run = getattr(job, "next_run_time", None)
        logger.info(f"  {job.name}: next run at {next_run}")
    logger.info("=" * 60)

    # Run initial analysis (may fail on empty DB, that is fine)
    logger.info("Running initial analysis...")
    try:
        run_analysis()
    except Exception as e:
        logger.warning(f"Initial analysis skipped (may be empty DB): {e}")

    logger.info("Scheduler starting...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shutting down...")


if __name__ == "__main__":
    main()
