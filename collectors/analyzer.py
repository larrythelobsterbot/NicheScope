"""Core analysis engine: trend velocity, niche scoring, breakout detection."""

import math
import sqlite3
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta

from config import DB_PATH, SCORE_WEIGHTS, ALERT_THRESHOLDS, get_active_keywords, get_categories

logger = logging.getLogger(__name__)


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def calculate_trend_velocity(keyword_id: int) -> dict:
    """Calculate trend velocity comparing current week to 4 and 12 weeks ago."""
    with get_db() as db:
        cursor = db.cursor()

        cursor.execute(
            """SELECT date, interest_score FROM trend_data
               WHERE keyword_id = ? AND interest_score IS NOT NULL
               ORDER BY date DESC LIMIT 13""",
            (keyword_id,),
        )
        rows = cursor.fetchall()

    if len(rows) < 2:
        return {"velocity_4w": 0.0, "velocity_12w": 0.0, "current": 0}

    current = rows[0]["interest_score"]
    four_weeks = rows[3]["interest_score"] if len(rows) > 3 else rows[-1]["interest_score"]
    twelve_weeks = rows[11]["interest_score"] if len(rows) > 11 else rows[-1]["interest_score"]

    four_weeks = max(four_weeks or 1, 1)
    twelve_weeks = max(twelve_weeks or 1, 1)

    return {
        "velocity_4w": round(((current / four_weeks) * 100) - 100, 1),
        "velocity_12w": round(((current / twelve_weeks) * 100) - 100, 1),
        "current": current,
    }


def detect_breakouts() -> list:
    """Detect keywords with week-over-week growth exceeding threshold."""
    breakouts = []
    threshold = ALERT_THRESHOLDS["trend_spike_pct"]

    with get_db() as db:
        cursor = db.cursor()

        cursor.execute("SELECT id, keyword, category FROM keywords WHERE is_active = 1")
        keywords = cursor.fetchall()

    for kw in keywords:
        velocity = calculate_trend_velocity(kw["id"])
        if velocity["velocity_4w"] > threshold:
            breakouts.append({
                "keyword": kw["keyword"],
                "category": kw["category"],
                "velocity_4w": velocity["velocity_4w"],
                "velocity_12w": velocity["velocity_12w"],
                "current_interest": velocity["current"],
                "severity": _classify_severity(velocity["velocity_4w"]),
            })

    breakouts.sort(key=lambda x: x["velocity_4w"], reverse=True)
    logger.info(f"Detected {len(breakouts)} breakout signals")
    return breakouts


def _classify_severity(velocity: float) -> str:
    if velocity > 200:
        return "critical"
    elif velocity > 100:
        return "warning"
    return "info"


def calculate_niche_scores():
    """Calculate composite niche scores for each category."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    scores = {}

    with get_db() as db:
        cursor = db.cursor()

        for category in get_categories():
            # Trend score: average velocity across category keywords
            trend_score = _calc_trend_score(cursor, category)

            # Margin score: based on price data and supplier costs
            margin_score = _calc_margin_score(cursor, category)

            # Competition score: fewer competitors with high traffic = better opportunity
            competition_score = _calc_competition_score(cursor, category)

            # Sourcing score: based on supplier quality and availability
            sourcing_score = _calc_sourcing_score(cursor, category)

            # Content score: based on TikTok engagement potential
            content_score = _calc_content_score(cursor, category)

            # Repeat purchase score: based on product category nature
            repeat_score = _calc_repeat_purchase_score(cursor, category)

            # Weighted overall score
            overall = (
                trend_score * SCORE_WEIGHTS["trend"]
                + margin_score * SCORE_WEIGHTS["margin"]
                + competition_score * SCORE_WEIGHTS["competition"]
                + sourcing_score * SCORE_WEIGHTS["sourcing"]
                + content_score * SCORE_WEIGHTS["content"]
                + repeat_score * SCORE_WEIGHTS["repeat_purchase"]
            )

            scores[category] = {
                "trend_score": round(trend_score, 1),
                "margin_score": round(margin_score, 1),
                "competition_score": round(competition_score, 1),
                "sourcing_score": round(sourcing_score, 1),
                "content_score": round(content_score, 1),
                "repeat_purchase_score": round(repeat_score, 1),
                "overall_score": round(overall, 1),
            }

            # Store snapshot
            cursor.execute(
                """INSERT OR REPLACE INTO niche_scores
                   (category, date, trend_score, margin_score, competition_score,
                    sourcing_score, content_score, repeat_purchase_score, overall_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    category, today,
                    scores[category]["trend_score"],
                    scores[category]["margin_score"],
                    scores[category]["competition_score"],
                    scores[category]["sourcing_score"],
                    scores[category]["content_score"],
                    scores[category]["repeat_purchase_score"],
                    scores[category]["overall_score"],
                ),
            )

        db.commit()

    logger.info(f"Niche scores calculated: {json.dumps(scores, indent=2)}")
    return scores


def _calc_trend_score(cursor, category: str) -> float:
    """Average trend velocity across all keywords in category (0-100 scale)."""
    cursor.execute("""
        SELECT k.id, td.interest_score, td.date,
               ROW_NUMBER() OVER (PARTITION BY k.id ORDER BY td.date DESC) as rn
        FROM keywords k
        JOIN trend_data td ON k.id = td.keyword_id
        WHERE k.category = ? AND k.is_active = 1
          AND td.interest_score IS NOT NULL
          AND td.date >= date('now', '-91 days')
        ORDER BY k.id, td.date DESC
    """, (category,))
    rows = cursor.fetchall()

    # Group by keyword_id
    keyword_data = {}
    for row in rows:
        kid = row["id"]
        rn = row["rn"]
        if kid not in keyword_data:
            keyword_data[kid] = {}
        keyword_data[kid][rn] = row["interest_score"]

    if not keyword_data:
        return 50.0

    velocities = []
    for kid, scores in keyword_data.items():
        current = scores.get(1, 0)
        four_weeks = scores.get(4, scores.get(max(scores.keys()), 1))
        four_weeks = max(four_weeks or 1, 1)
        velocity = ((current / four_weeks) * 100) - 100
        velocities.append(velocity)

    avg_velocity = sum(velocities) / len(velocities)
    return max(0, min(100, 50 + (avg_velocity / 2)))


def _calc_margin_score(cursor, category: str) -> float:
    """Estimate margin potential from price data vs supplier costs (0-100)."""
    # Get average retail price from product history
    cursor.execute(
        """SELECT AVG(ph.price) as avg_price
           FROM product_history ph
           JOIN products p ON ph.product_id = p.id
           WHERE p.category = ? AND ph.price > 0""",
        (category,),
    )
    row = cursor.fetchone()
    avg_retail = row["avg_price"] if row and row["avg_price"] else 0

    # Get supplier costs - prefer structured prices, fall back to string parsing
    cursor.execute(
        """SELECT price_low, price_high, price_range FROM suppliers
           WHERE product_focus LIKE ?""",
        (f"%{category}%",),
    )
    suppliers = cursor.fetchall()

    if not avg_retail or not suppliers:
        defaults = {"beauty": 75, "jewelry": 80, "travel": 60}
        return defaults.get(category, 50)

    avg_cost = 0
    count = 0
    for s in suppliers:
        # Prefer structured price columns
        if s["price_low"] is not None and s["price_high"] is not None:
            avg_cost += (s["price_low"] + s["price_high"]) / 2
            count += 1
        elif s["price_range"] and "$" in s["price_range"]:
            # Fallback to string parsing
            try:
                parts = s["price_range"].replace("$", "").replace("/unit", "").split("-")
                low = float(parts[0])
                high = float(parts[1]) if len(parts) > 1 else low
                avg_cost += (low + high) / 2
                count += 1
            except (ValueError, IndexError):
                pass

    if count > 0:
        avg_cost = avg_cost / count
        margin_pct = ((avg_retail - avg_cost) / avg_retail) * 100 if avg_retail > 0 else 0
        # Normalize: 30% margin = 50, 70% = 100, <10% = 0
        return max(0, min(100, (margin_pct - 10) * (100 / 60)))

    return 50.0


def _calc_competition_score(cursor, category: str) -> float:
    """Lower competition = higher score (0-100)."""
    cursor.execute(
        """SELECT COUNT(*) as cnt, AVG(ct.visits_estimate) as avg_traffic
           FROM competitors c
           LEFT JOIN competitor_traffic ct ON c.id = ct.competitor_id
           WHERE c.category = ?""",
        (category,),
    )
    row = cursor.fetchone()
    num_competitors = row["cnt"] if row else 0
    avg_traffic = row["avg_traffic"] if row and row["avg_traffic"] else 0

    # Fewer competitors with lower traffic = higher opportunity score
    comp_penalty = min(num_competitors * 10, 50)
    traffic_penalty = min(avg_traffic / 10000, 50) if avg_traffic else 0

    return max(0, 100 - comp_penalty - traffic_penalty)


def _calc_sourcing_score(cursor, category: str) -> float:
    """Score based on supplier quality and availability (0-100)."""
    cursor.execute(
        """SELECT AVG(quality_score) as avg_quality, COUNT(*) as cnt
           FROM suppliers
           WHERE product_focus LIKE ?""",
        (f"%{category}%",),
    )
    row = cursor.fetchone()

    if not row or row["cnt"] == 0:
        return 40.0

    quality = (row["avg_quality"] or 5) * 10  # Scale 1-10 to 10-100
    availability_bonus = min(row["cnt"] * 10, 30)  # More suppliers = better

    return min(100, quality + availability_bonus)


def _calc_content_score(cursor, category: str) -> float:
    """Score based on TikTok engagement potential (0-100)."""
    keywords = get_active_keywords().get(category, [])
    if not keywords:
        return 50.0

    placeholders = ",".join("?" * len(keywords))
    cursor.execute(
        f"""SELECT AVG(view_count) as avg_views, AVG(ad_count) as avg_ads
            FROM tiktok_trends
            WHERE keyword IN ({placeholders})
            AND date >= date('now', '-30 days')""",
        keywords,
    )
    row = cursor.fetchone()

    if not row or not row["avg_views"]:
        defaults = {"beauty": 80, "jewelry": 60, "travel": 55}
        return defaults.get(category, 50)

    # Logarithmic scale: 1K=20, 10K=40, 100K=60, 1M=80, 10M=100
    avg_views = row["avg_views"] or 0
    if avg_views > 0:
        view_score = min(100, max(0, (math.log10(avg_views) - 3) * 20))
    else:
        view_score = 0

    # Some ads = validated market, too many = saturated
    ad_score = 50
    if row["avg_ads"]:
        if row["avg_ads"] < 10:
            ad_score = 70
        elif row["avg_ads"] < 50:
            ad_score = 60
        else:
            ad_score = 30

    return (view_score + ad_score) / 2


def _calc_repeat_purchase_score(cursor, category: str) -> float:
    """Repeat purchase potential — DB-driven with sensible fallbacks."""
    # Check for a stored repeat_score in the categories table
    try:
        cursor.execute(
            "SELECT repeat_score FROM categories WHERE name = ? AND repeat_score IS NOT NULL",
            (category,),
        )
        row = cursor.fetchone()
        if row and row["repeat_score"] is not None:
            return float(row["repeat_score"])
    except Exception:
        pass  # Column may not exist yet

    # Fallback: domain knowledge defaults
    defaults = {
        "beauty": 85,
        "jewelry": 50,
        "travel": 35,
        "pets": 75,
        "food": 90,
        "fitness": 60,
        "home": 40,
        "tech_accessories": 30,
    }
    return defaults.get(category, 50)


def generate_alerts(breakouts: list, price_anomalies: list = None):
    """Store alerts in the database for dashboard display."""
    with get_db() as db:
        cursor = db.cursor()

        for b in breakouts:
            cursor.execute(
                """INSERT INTO alerts (type, severity, message, data)
                   VALUES (?, ?, ?, ?)""",
                (
                    "breakout",
                    b["severity"],
                    f"'{b['keyword']}' trending +{b['velocity_4w']}% in {b['category']}",
                    json.dumps(b),
                ),
            )

        if price_anomalies:
            for a in price_anomalies:
                alert_type = a.get("type", "price_drop")
                if alert_type == "price_drop":
                    cursor.execute(
                        """INSERT INTO alerts (type, severity, message, data)
                           VALUES (?, ?, ?, ?)""",
                        (
                            "price_drop",
                            "warning",
                            f"{a['title'][:40]} dropped {a['drop_pct']}% to ${a['current_price']:.2f}",
                            json.dumps(a),
                        ),
                    )
                elif alert_type == "stock_out":
                    cursor.execute(
                        """INSERT INTO alerts (type, severity, message, data)
                           VALUES (?, ?, ?, ?)""",
                        (
                            "stock_out",
                            "info",
                            f"{a['title'][:40]} is out of stock",
                            json.dumps(a),
                        ),
                    )

        db.commit()


def run_analysis():
    """Run the full analysis pipeline."""
    logger.info("Starting analysis pipeline...")

    # 1. Detect breakouts
    breakouts = detect_breakouts()

    # 2. Calculate niche scores
    scores = calculate_niche_scores()

    # 3. Generate alerts
    generate_alerts(breakouts)

    logger.info("Analysis pipeline complete.")
    return {"breakouts": breakouts, "scores": scores}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = run_analysis()
    print(f"\nBreakouts: {len(results['breakouts'])}")
    for b in results["breakouts"][:5]:
        print(f"  {b['keyword']} ({b['category']}): +{b['velocity_4w']}%")
    print(f"\nScores:")
    for cat, s in results["scores"].items():
        print(f"  {cat}: {s['overall_score']}/100")
