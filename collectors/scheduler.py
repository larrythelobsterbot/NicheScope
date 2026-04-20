"""
APScheduler orchestrator for all NicheScope data collection jobs.
Production-ready: loads .env, logs everything, tracks collector health,
alerts on repeated failures via Telegram. Never crashes.
"""

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
from keepa_collector import collect_products, detect_anomalies
from tiktok_trends import collect_tiktok_trends
from alibaba_collector import collect_alibaba_suppliers
from similarweb import collect_competitor_traffic
from analyzer import run_analysis, detect_breakouts
from discovery import run_discovery
from reddit_discovery import discover_from_reddit
from etsy_discovery import discover_from_etsy
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


def record_collector_health(collector_name, success=True, error=None):
    """Update the collector_health table after a job runs."""
    try:
        db = get_health_db()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        if success:
            db.execute("""
                INSERT INTO collector_health
                    (collector_name, last_run, last_success, consecutive_failures,
                     total_runs, total_successes, updated_at)
                VALUES (?, ?, ?, 0, 1, 1, ?)
                ON CONFLICT(collector_name) DO UPDATE SET
                    last_run = ?,
                    last_success = ?,
                    last_error = NULL,
                    consecutive_failures = 0,
                    total_runs = total_runs + 1,
                    total_successes = total_successes + 1,
                    updated_at = ?
            """, (collector_name, now, now, now, now, now, now))
        else:
            error_msg = str(error)[:500] if error else "Unknown error"
            db.execute("""
                INSERT INTO collector_health
                    (collector_name, last_run, last_error, consecutive_failures,
                     total_runs, total_successes, updated_at)
                VALUES (?, ?, ?, 1, 1, 0, ?)
                ON CONFLICT(collector_name) DO UPDATE SET
                    last_run = ?,
                    last_error = ?,
                    consecutive_failures = consecutive_failures + 1,
                    total_runs = total_runs + 1,
                    updated_at = ?
            """, (collector_name, now, error_msg, now, now, error_msg, now))

        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Failed to record health for {collector_name}: {e}")


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
    """Log job execution results and track health."""
    job_id = event.job_id

    if event.exception:
        logger.error(f"Job '{job_id}' failed: {event.exception}")
        record_collector_health(job_id, success=False, error=str(event.exception))
        check_and_alert_failures(job_id)
    else:
        logger.info(f"Job '{job_id}' completed successfully")
        record_collector_health(job_id, success=True)


# ============================================================
# Job Wrappers (each catches its own exceptions)
# ============================================================

def job_google_trends():
    logger.info("=== Google Trends collection started ===")
    try:
        count = collect_trends()
        logger.info(f"Google Trends: {count} data points collected")
        run_post_collection()
    except Exception as e:
        logger.error(f"Google Trends job failed: {e}", exc_info=True)
        raise


def job_keepa():
    logger.info("=== Keepa collection started ===")
    try:
        count = collect_products()
        logger.info(f"Keepa: {count} products updated")
        anomalies = detect_anomalies()
        for anomaly in anomalies:
            send_price_alert(anomaly)
        run_post_collection()
    except Exception as e:
        logger.error(f"Keepa job failed: {e}", exc_info=True)
        raise


def job_tiktok():
    logger.info("=== TikTok trends collection started ===")
    try:
        count = collect_tiktok_trends()
        logger.info(f"TikTok: {count} keywords processed")
        run_post_collection()
    except Exception as e:
        logger.error(f"TikTok job failed: {e}", exc_info=True)
        raise


def job_alibaba():
    logger.info("=== Alibaba supplier scan started ===")
    try:
        count = collect_alibaba_suppliers()
        logger.info(f"Alibaba: {count} new suppliers discovered")
    except Exception as e:
        logger.error(f"Alibaba job failed: {e}", exc_info=True)
        raise


def job_competitor_traffic():
    logger.info("=== Competitor traffic collection started ===")
    try:
        count = collect_competitor_traffic()
        logger.info(f"SimilarWeb: {count} domains updated")
    except Exception as e:
        logger.error(f"Competitor traffic job failed: {e}", exc_info=True)
        raise


def job_daily_digest():
    logger.info("=== Daily digest job started ===")
    try:
        send_daily_digest()
        logger.info("Daily digest sent")
    except Exception as e:
        logger.error(f"Daily digest job failed: {e}", exc_info=True)
        raise


def job_weekly_analysis():
    logger.info("=== Weekly deep analysis started ===")
    try:
        results = run_analysis()
        for b in results.get("breakouts", []):
            if b["severity"] == "critical":
                send_breakout_alert(b)
        logger.info("Weekly analysis complete")
    except Exception as e:
        logger.error(f"Weekly analysis failed: {e}", exc_info=True)
        raise


def job_telegram_poll():
    """Poll Telegram for incoming commands."""
    try:
        poll_for_commands()
    except Exception as e:
        logger.error(f"Telegram poll failed: {e}")


def job_discovery_categories():
    logger.info("=== Discovery: category scan started ===")
    try:
        count = run_discovery()
        logger.info(f"Discovery: {count} new pending keywords")
        send_discovery_digest()
    except Exception as e:
        logger.error(f"Discovery category scan failed: {e}", exc_info=True)
        raise


def job_discovery_related():
    logger.info("=== Discovery: related queries scan started ===")
    try:
        from discovery import discover_from_related_queries
        count = discover_from_related_queries()
        logger.info(f"Related queries discovery: {count} new pending keywords")
        send_discovery_digest()
    except Exception as e:
        logger.error(f"Related queries discovery failed: {e}", exc_info=True)
        raise


def job_reddit_discovery():
    logger.info("=== Reddit discovery started ===")
    try:
        count = discover_from_reddit()
        logger.info(f"Reddit discovery: {count} new pending keywords")
        send_discovery_digest()
    except Exception as e:
        logger.error(f"Reddit discovery failed: {e}", exc_info=True)
        raise


def job_etsy_discovery():
    logger.info("=== Etsy discovery started ===")
    try:
        count = discover_from_etsy()
        logger.info(f"Etsy discovery: {count} new pending keywords")
        send_discovery_digest()
    except Exception as e:
        logger.error(f"Etsy discovery failed: {e}", exc_info=True)
        raise


def run_post_collection():
    """Run analysis after a collector finishes."""
    try:
        results = run_analysis()
        for b in results.get("breakouts", []):
            if b["severity"] == "critical":
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

def main():
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

    # Keepa: every 6 hours (only if API key is configured)
    if os.getenv("KEEPA_API_KEY"):
        scheduler.add_job(
            job_keepa,
            IntervalTrigger(hours=SCHEDULE["keepa"]["hours"]),
            id="keepa",
            name="Keepa Product Collector",
            misfire_grace_time=1800,
            coalesce=True,
        )
    else:
        logger.info("KEEPA_API_KEY not set. Keepa collector disabled.")

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

    # Daily Telegram digest: 9am HKT
    if os.getenv("TELEGRAM_BOT_TOKEN"):
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

        # Telegram command polling: every 30 seconds
        scheduler.add_job(
            job_telegram_poll,
            IntervalTrigger(seconds=30),
            id="telegram_poll",
            name="Telegram Command Poller",
        )
    else:
        logger.info("TELEGRAM_BOT_TOKEN not set. Telegram features disabled.")

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

    # Graceful shutdown
    def shutdown(signum, frame):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

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

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shutting down...")


if __name__ == "__main__":
    main()
