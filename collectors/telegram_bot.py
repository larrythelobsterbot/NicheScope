"""Telegram bot for NicheScope alerts, daily digests, and /add /remove /status commands."""

import json
import logging
import sqlite3
from datetime import datetime

import httpx

from config import DB_PATH, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, get_active_keywords, get_categories
from analyzer import detect_breakouts, calculate_niche_scores

logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def send_telegram(message: str) -> bool:
    """Send a message via Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured. Message not sent.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    try:
        with httpx.Client(timeout=15) as client:
            response = client.post(
                url,
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()
            logger.info("Telegram message sent.")
            return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


def format_daily_digest() -> str:
    """Generate the daily digest message."""
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """SELECT k.keyword, k.category, td.interest_score
           FROM keywords k
           JOIN trend_data td ON k.id = td.keyword_id
           WHERE td.date = (SELECT MAX(date) FROM trend_data)
           ORDER BY td.interest_score DESC
           LIMIT 5"""
    )
    top_keywords = cursor.fetchall()

    cursor.execute(
        """SELECT message, severity FROM alerts
           WHERE type = 'breakout'
           AND sent_at >= datetime('now', '-24 hours')
           ORDER BY sent_at DESC
           LIMIT 5"""
    )
    recent_alerts = cursor.fetchall()

    cursor.execute(
        """SELECT category, overall_score, trend_score
           FROM niche_scores
           WHERE date = (SELECT MAX(date) FROM niche_scores)
           ORDER BY overall_score DESC"""
    )
    scores = cursor.fetchall()

    # Pending keywords count
    cursor.execute("SELECT COUNT(*) FROM pending_keywords WHERE status = 'pending'")
    pending_count = cursor.fetchone()[0]

    db.close()

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    categories = get_categories()
    lines = [
        f"<b>NicheScope Daily Digest</b>",
        f"<i>{now}</i>",
        f"Tracking {len(categories)} categories",
        "",
    ]

    lines.append("<b>Top Trending Keywords:</b>")
    if top_keywords:
        emojis = ["1\ufe0f\u20e3", "2\ufe0f\u20e3", "3\ufe0f\u20e3", "4\ufe0f\u20e3", "5\ufe0f\u20e3"]
        for i, kw in enumerate(top_keywords):
            lines.append(
                f"{emojis[i]} {kw['keyword']} ({kw['category']}) - Score: {kw['interest_score']}"
            )
    else:
        lines.append("  No data yet.")
    lines.append("")

    if recent_alerts:
        lines.append("<b>Breakout Signals:</b>")
        for alert in recent_alerts:
            emoji = {
                "critical": "\U0001f525", "warning": "\u26a0\ufe0f", "info": "\u2139\ufe0f"
            }.get(alert["severity"], "\u2139\ufe0f")
            lines.append(f"{emoji} {alert['message']}")
        lines.append("")

    if scores:
        lines.append("<b>Niche Rankings:</b>")
        for i, s in enumerate(scores, 1):
            bar = "\u2588" * int(s["overall_score"] / 10) + "\u2591" * (10 - int(s["overall_score"] / 10))
            lines.append(f"  {i}. {s['category'].title()} [{bar}] {s['overall_score']}/100")

    if pending_count > 0:
        lines.append(f"\n\U0001f4ac {pending_count} discovered keywords awaiting approval")

    lines.append("\n<i>/add category \"keyword\" to track new keywords</i>")

    return "\n".join(lines)


def send_daily_digest():
    """Send the daily digest via Telegram."""
    return send_telegram(format_daily_digest())


def send_discovery_digest():
    """Send a digest of newly discovered keywords (if any)."""
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """SELECT keyword, suggested_category, relevance_score
           FROM pending_keywords
           WHERE status = 'pending'
             AND discovered_at >= datetime('now', '-24 hours')
           ORDER BY relevance_score DESC
           LIMIT 15"""
    )
    new_pending = cursor.fetchall()
    db.close()

    if not new_pending:
        return

    lines = [
        f"<b>NicheScope discovered {len(new_pending)} new trending keywords overnight:</b>",
        "",
    ]
    for kw in new_pending:
        score = round(kw["relevance_score"], 2) if kw["relevance_score"] else 0
        lines.append(f"- {kw['keyword']} ({kw['suggested_category']}, score: {score})")

    lines.append("")
    lines.append("Open the admin panel to review and approve.")

    send_telegram("\n".join(lines))


def send_breakout_alert(breakout: dict):
    """Send an instant breakout alert."""
    emoji = {
        "critical": "\U0001f525\U0001f525\U0001f525", "warning": "\u26a0\ufe0f", "info": "\u2139\ufe0f"
    }.get(breakout.get("severity", "info"), "\u2139\ufe0f")

    message = (
        f"{emoji} <b>BREAKOUT SIGNAL</b>\n\n"
        f"<b>{breakout['keyword']}</b> ({breakout['category']})\n"
        f"4-week velocity: +{breakout['velocity_4w']}%\n"
        f"12-week velocity: +{breakout['velocity_12w']}%\n"
        f"Current interest: {breakout['current_interest']}/100\n\n"
        f"<i>Check NicheScope dashboard for details.</i>"
    )
    return send_telegram(message)


def send_price_alert(anomaly: dict):
    """Send a price drop or stock-out alert."""
    if anomaly["type"] == "price_drop":
        message = (
            f"\U0001f4c9 <b>Price Drop Alert</b>\n\n"
            f"{anomaly['title'][:60]}\n"
            f"ASIN: {anomaly['asin']}\n"
            f"Price: ${anomaly['prev_price']:.2f} -> ${anomaly['current_price']:.2f} (-{anomaly['drop_pct']}%)\n"
        )
    else:
        message = (
            f"\U0001f6d1 <b>Stock Out Alert</b>\n\n"
            f"{anomaly['title'][:60]}\n"
            f"ASIN: {anomaly['asin']}\n"
            f"Status: Out of stock\n"
        )
    return send_telegram(message)


# ============================================================
# Command Handlers: /add, /remove, /status
# ============================================================

def handle_add_command(text: str) -> str:
    """Handle /add category "keyword" command.

    Examples:
        /add beauty "holographic nails"
        /add electronics "wireless earbuds"
    """
    parts = text.strip().split(maxsplit=2)
    if len(parts) < 3:
        return "Usage: /add category \"keyword\"\nExample: /add beauty \"holographic nails\""

    category = parts[1].lower().strip()
    keyword = parts[2].strip().strip('"').strip("'")

    if not keyword:
        return "Please provide a keyword to add."

    db = get_db()
    try:
        # Ensure category exists
        db.execute(
            "INSERT OR IGNORE INTO categories (name) VALUES (?)", (category,)
        )
        # Insert keyword
        db.execute(
            "INSERT OR IGNORE INTO keywords (keyword, category) VALUES (?, ?)",
            (keyword, category),
        )
        db.commit()
        db.close()

        active = get_active_keywords()
        count = sum(len(v) for v in active.values())
        return (
            f"\u2705 Added '<b>{keyword}</b>' to <b>{category}</b>\n"
            f"Now tracking {count} keywords across {len(active)} categories.\n"
            f"Next collector run will pick it up automatically."
        )
    except Exception as e:
        db.close()
        return f"\u274c Failed to add keyword: {e}"


def handle_remove_command(text: str) -> str:
    """Handle /remove "keyword" command."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return "Usage: /remove \"keyword\""

    keyword = parts[1].strip().strip('"').strip("'")

    db = get_db()
    try:
        db.execute(
            "UPDATE keywords SET is_active = 0 WHERE keyword = ?", (keyword,)
        )
        db.commit()
        affected = db.total_changes
        db.close()

        if affected > 0:
            return f"\u2705 Deactivated '<b>{keyword}</b>' from tracking."
        else:
            return f"\u26a0\ufe0f Keyword '{keyword}' not found in database."
    except Exception as e:
        db.close()
        return f"\u274c Failed to remove keyword: {e}"


def handle_status_command() -> str:
    """Handle /status command. Shows collector health and stats."""
    db = get_db()
    cursor = db.cursor()

    # Category counts
    cursor.execute(
        "SELECT category, COUNT(*) as cnt FROM keywords WHERE is_active = 1 GROUP BY category ORDER BY cnt DESC"
    )
    cat_counts = cursor.fetchall()

    # Latest collection timestamps
    cursor.execute("SELECT MAX(collected_at) FROM trend_data")
    last_trends = cursor.fetchone()[0] or "Never"

    cursor.execute("SELECT MAX(collected_at) FROM product_history")
    last_keepa = cursor.fetchone()[0] or "Never"

    cursor.execute("SELECT MAX(collected_at) FROM tiktok_trends")
    last_tiktok = cursor.fetchone()[0] or "Never"

    # Alert count
    cursor.execute("SELECT COUNT(*) FROM alerts WHERE sent_at >= datetime('now', '-24 hours')")
    alerts_24h = cursor.fetchone()[0]

    # Pending keywords
    cursor.execute("SELECT COUNT(*) FROM pending_keywords WHERE status = 'pending'")
    pending = cursor.fetchone()[0]

    db.close()

    lines = [
        "<b>NicheScope Status</b>",
        "",
        "<b>Categories:</b>",
    ]
    for row in cat_counts:
        lines.append(f"  {row['category'].title()}: {row['cnt']} keywords")

    lines.extend([
        "",
        "<b>Last Collection:</b>",
        f"  Google Trends: {last_trends}",
        f"  Keepa: {last_keepa}",
        f"  TikTok: {last_tiktok}",
        "",
        f"Alerts (24h): {alerts_24h}",
        f"Pending keywords: {pending}",
        "",
        "<i>Commands: /add, /remove, /status</i>",
    ])
    return "\n".join(lines)


def process_incoming_message(text: str) -> str:
    """Route incoming Telegram messages to the appropriate handler."""
    text = text.strip()
    if text.startswith("/add"):
        return handle_add_command(text)
    elif text.startswith("/remove"):
        return handle_remove_command(text)
    elif text.startswith("/status"):
        return handle_status_command()
    else:
        return (
            "Available commands:\n"
            "/add category \"keyword\" - Track a new keyword\n"
            "/remove \"keyword\" - Stop tracking a keyword\n"
            "/status - Show collector health and stats"
        )


def poll_for_commands():
    """Poll Telegram for incoming commands (long polling)."""
    if not TELEGRAM_BOT_TOKEN:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    offset = 0

    try:
        with httpx.Client(timeout=35) as client:
            response = client.get(url, params={"offset": offset, "timeout": 30})
            data = response.json()

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message", {})
                text = message.get("text", "")
                chat_id = message.get("chat", {}).get("id")

                if text and chat_id:
                    reply = process_incoming_message(text)
                    client.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": reply,
                            "parse_mode": "HTML",
                        },
                    )

            # Acknowledge processed updates
            if offset:
                client.get(url, params={"offset": offset})

    except Exception as e:
        logger.error(f"Telegram polling error: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    digest = format_daily_digest()
    print(digest)
    print("\nTo send via Telegram, set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars.")
