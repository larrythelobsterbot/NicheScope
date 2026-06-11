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


# Trend metric tuning. Weekly data points, newest first.
METRIC_WINDOWS = {
    "history_weeks": 56,      # fetch horizon (covers YoY comparison)
    "yoy_offset": 49,         # rows ~52 weeks ago: indexes [49, 56)
    "yoy_window": 7,          # +/- a few weeks absorbs Google's weekly bucket drift
    "yoy_min_rows": 55,       # minimum history for a YoY figure
    "z_threshold": 2.0,       # breakout needs current > mean + 2 sigma
    "seasonal_yoy_flat_pct": 15.0,  # YoY below this while 4w spikes => seasonal
}


def _mean(values):
    values = [v for v in values if v is not None]
    return (sum(values) / len(values)) if values else None


def _pct_change(current, baseline):
    baseline = max(baseline or 1, 1)
    return round(((current / baseline) * 100) - 100, 1)


def _classify_lifecycle(current: float, velocity_4w: float, velocity_12w: float) -> str:
    """Classify where a keyword sits in its trend lifecycle."""
    if velocity_4w <= -10:
        return "declining"
    if velocity_4w >= 10:
        # Rising from a low base = early; rising while already established = hot
        return "emerging" if current < 30 else "accelerating"
    if velocity_12w >= 25:
        return "peaking"  # rose over the quarter, now flat at the top
    return "stable"


def _metrics_from_scores(scores: list) -> dict:
    """Compute trend metrics from a keyword's interest scores, newest first.

    Velocities compare window averages, not single points: one noisy week
    against another produced most of the old false breakouts.
    """
    if len(scores) < 2:
        return {
            "velocity_4w": 0.0, "velocity_12w": 0.0, "velocity_yoy": None,
            "current": scores[0] if scores else 0,
            "z_score": 0.0, "is_seasonal": False, "lifecycle": "stable",
        }

    current = _mean(scores[0:2])
    baseline_4w = _mean(scores[4:7]) or _mean(scores[-2:])
    baseline_12w = _mean(scores[10:13]) or baseline_4w

    velocity_4w = _pct_change(current, baseline_4w)
    velocity_12w = _pct_change(current, baseline_12w)

    # Z-score of the latest point against its own trailing 12 weeks
    trailing = scores[1:13]
    z_score = 0.0
    if len(trailing) >= 4:
        mean = _mean(trailing)
        variance = sum((s - mean) ** 2 for s in trailing) / len(trailing)
        std = max(variance ** 0.5, 1.0)  # floor: don't divide by near-zero on flat series
        z_score = round((scores[0] - mean) / std, 2)

    # Year-over-year, peak-to-peak: current level vs last year's local
    # maximum around the same week. A mean would dilute last year's spike
    # with its shoulder weeks and make recurring seasonal peaks look like
    # genuine growth.
    velocity_yoy = None
    if len(scores) >= METRIC_WINDOWS["yoy_min_rows"]:
        start = METRIC_WINDOWS["yoy_offset"]
        window = [s for s in scores[start:start + METRIC_WINDOWS["yoy_window"]] if s is not None]
        if window:
            velocity_yoy = _pct_change(current, max(window))

    # Seasonal: spiking vs a month ago but flat vs the same time last year
    is_seasonal = (
        velocity_yoy is not None
        and velocity_4w > ALERT_THRESHOLDS["trend_spike_pct"]
        and velocity_yoy < METRIC_WINDOWS["seasonal_yoy_flat_pct"]
    )

    return {
        "velocity_4w": velocity_4w,
        "velocity_12w": velocity_12w,
        "velocity_yoy": velocity_yoy,
        "current": scores[0],
        "z_score": z_score,
        "is_seasonal": is_seasonal,
        "lifecycle": _classify_lifecycle(scores[0], velocity_4w, velocity_12w),
    }


def calculate_trend_velocity(keyword_id: int) -> dict:
    """Compute trend metrics for one keyword (window-averaged velocities)."""
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute(
            """SELECT interest_score FROM trend_data
               WHERE keyword_id = ? AND interest_score IS NOT NULL
               ORDER BY date DESC LIMIT ?""",
            (keyword_id, METRIC_WINDOWS["history_weeks"]),
        )
        scores = [r["interest_score"] for r in cursor.fetchall()]
    return _metrics_from_scores(scores)


def compute_all_metrics() -> dict:
    """Compute metrics for every active keyword in one pass and persist them.

    Returns {keyword_id: {keyword, category, **metrics}}. Written to the
    keyword_metrics table so the frontend reads the same numbers the
    analyzer alerts on, instead of re-deriving its own.
    """
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute(
            """SELECT keyword_id, interest_score FROM (
                   SELECT td.keyword_id, td.date, td.interest_score,
                          ROW_NUMBER() OVER (
                              PARTITION BY td.keyword_id ORDER BY td.date DESC
                          ) AS rn
                   FROM trend_data td
                   JOIN keywords k ON k.id = td.keyword_id
                   WHERE k.is_active = 1 AND td.interest_score IS NOT NULL
               ) WHERE rn <= ?
               ORDER BY keyword_id, rn""",
            (METRIC_WINDOWS["history_weeks"],),
        )
        series = {}
        for row in cursor.fetchall():
            series.setdefault(row["keyword_id"], []).append(row["interest_score"])

        cursor.execute("SELECT id, keyword, category FROM keywords WHERE is_active = 1")
        keywords = {r["id"]: r for r in cursor.fetchall()}

        now = datetime.utcnow().isoformat(timespec="seconds")
        metrics = {}
        persist = True
        for kid, kw in keywords.items():
            m = _metrics_from_scores(series.get(kid, []))
            m["keyword"] = kw["keyword"]
            m["category"] = kw["category"]
            metrics[kid] = m

            if not persist:
                continue
            try:
                cursor.execute(
                    """INSERT INTO keyword_metrics
                           (keyword_id, computed_at, current_interest, velocity_4w,
                            velocity_12w, velocity_yoy, z_score, is_seasonal, lifecycle)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(keyword_id) DO UPDATE SET
                           computed_at = excluded.computed_at,
                           current_interest = excluded.current_interest,
                           velocity_4w = excluded.velocity_4w,
                           velocity_12w = excluded.velocity_12w,
                           velocity_yoy = excluded.velocity_yoy,
                           z_score = excluded.z_score,
                           is_seasonal = excluded.is_seasonal,
                           lifecycle = excluded.lifecycle""",
                    (
                        kid, now, m["current"], m["velocity_4w"], m["velocity_12w"],
                        m["velocity_yoy"], m["z_score"], int(m["is_seasonal"]),
                        m["lifecycle"],
                    ),
                )
            except sqlite3.OperationalError:
                persist = False
                logger.warning(
                    "keyword_metrics table missing — run scripts/migrate_004_keyword_metrics.py"
                )

        db.commit()

    logger.info(f"Computed metrics for {len(metrics)} keywords")
    return metrics


def detect_breakouts(metrics: dict = None) -> list:
    """Detect genuine breakouts: big 4-week move, statistically unusual
    for the keyword, on meaningful interest. Seasonal spikes are kept but
    tagged and capped at info severity."""
    threshold = ALERT_THRESHOLDS["trend_spike_pct"]
    min_interest = ALERT_THRESHOLDS["min_interest"]

    if metrics is None:
        metrics = compute_all_metrics()

    breakouts = []
    for kid, m in metrics.items():
        if m["current"] < min_interest:
            continue  # percent moves on near-zero interest are noise
        if m["velocity_4w"] <= threshold:
            continue
        if m["z_score"] < METRIC_WINDOWS["z_threshold"]:
            continue  # within the keyword's normal variance — just a wobble

        severity = _classify_severity(m["velocity_4w"])
        if m["is_seasonal"]:
            severity = "info"  # expected annual pattern, never page on it

        breakouts.append({
            "keyword": m["keyword"],
            "category": m["category"],
            "velocity_4w": m["velocity_4w"],
            "velocity_12w": m["velocity_12w"],
            "velocity_yoy": m["velocity_yoy"],
            "z_score": m["z_score"],
            "is_seasonal": m["is_seasonal"],
            "lifecycle": m["lifecycle"],
            "current_interest": m["current"],
            "severity": severity,
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
    """Score based on YouTube content volume for category keywords (0-100)."""
    # Aggregate the most recent content_trends row per keyword in this category
    cursor.execute(
        """SELECT AVG(ct.avg_views_per_video)  AS avg_views,
                  AVG(ct.video_count_7d)        AS avg_velocity,
                  COUNT(*)                      AS n
           FROM keywords k
           JOIN content_trends ct ON ct.keyword_id = k.id
           WHERE k.category = ? AND k.is_active = 1
             AND ct.collected_at >= datetime('now', '-30 days')""",
        (category,),
    )
    row = cursor.fetchone()

    if not row or not row["n"]:
        defaults = {"beauty": 80, "jewelry": 60, "travel": 55}
        return defaults.get(category, 50)

    avg_views = row["avg_views"] or 0
    velocity = row["avg_velocity"] or 0

    # Volume component: log-scaled average views per video.
    # 1K=20, 10K=40, 100K=60, 1M=80, 10M=100.
    if avg_views > 0:
        view_score = min(100, max(0, (math.log10(avg_views) - 3) * 20))
    else:
        view_score = 0

    # Velocity component: more videos published in last 7 days = hotter topic.
    # 0=30, 3=60, 5+=90.
    if velocity >= 5:
        velocity_score = 90
    elif velocity >= 3:
        velocity_score = 60
    elif velocity >= 1:
        velocity_score = 45
    else:
        velocity_score = 30

    return (view_score + velocity_score) / 2


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


def _is_duplicate_alert(cursor, alert_type: str, subject_field: str, subject: str) -> bool:
    """True if an alert of this type for this subject exists within the dedup window."""
    dedup_days = ALERT_THRESHOLDS["alert_dedup_days"]
    cursor.execute(
        f"""SELECT 1 FROM alerts
            WHERE type = ?
              AND json_extract(data, '$.{subject_field}') = ?
              AND sent_at >= datetime('now', '-{int(dedup_days)} days')
            LIMIT 1""",
        (alert_type, subject),
    )
    return cursor.fetchone() is not None


def generate_alerts(breakouts: list, price_anomalies: list = None) -> dict:
    """Store alerts in the database for dashboard display.

    Deduplicates: the same keyword/ASIN does not re-alert within the dedup
    window even though analysis runs several times a day. Each breakout dict
    is tagged with "is_new"; callers should only notify on new ones.

    Returns {"new_breakouts": [...], "new_price_alerts": [...]}.
    """
    new_breakouts = []
    new_price_alerts = []

    with get_db() as db:
        cursor = db.cursor()

        for b in breakouts:
            if _is_duplicate_alert(cursor, "breakout", "keyword", b["keyword"]):
                b["is_new"] = False
                continue
            b["is_new"] = True
            seasonal_tag = " (seasonal)" if b.get("is_seasonal") else ""
            cursor.execute(
                """INSERT INTO alerts (type, severity, message, data)
                   VALUES (?, ?, ?, ?)""",
                (
                    "breakout",
                    b["severity"],
                    f"'{b['keyword']}' trending +{b['velocity_4w']}% in {b['category']}{seasonal_tag}",
                    json.dumps(b),
                ),
            )
            new_breakouts.append(b)

        if price_anomalies:
            for a in price_anomalies:
                alert_type = a.get("type", "price_drop")
                if _is_duplicate_alert(cursor, alert_type, "asin", a.get("asin", "")):
                    continue
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
                    new_price_alerts.append(a)
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
                    new_price_alerts.append(a)

        db.commit()

    return {"new_breakouts": new_breakouts, "new_price_alerts": new_price_alerts}


def expire_old_alerts() -> int:
    """Auto-acknowledge unread alerts older than the expiry window."""
    expiry_days = ALERT_THRESHOLDS["alert_expiry_days"]
    with get_db() as db:
        cursor = db.execute(
            f"""UPDATE alerts SET acknowledged = 1
                WHERE acknowledged = 0
                  AND sent_at < datetime('now', '-{int(expiry_days)} days')"""
        )
        db.commit()
        expired = cursor.rowcount
    if expired:
        logger.info(f"Auto-acknowledged {expired} alerts older than {expiry_days} days")
    return expired


def run_analysis():
    """Run the full analysis pipeline."""
    logger.info("Starting analysis pipeline...")

    # 1. Compute per-keyword metrics (persisted for the dashboard), then
    #    detect breakouts from them
    metrics = compute_all_metrics()
    breakouts = detect_breakouts(metrics)

    # 2. Calculate niche scores
    scores = calculate_niche_scores()

    # 3. Generate alerts (deduplicated; tags each breakout with "is_new")
    generate_alerts(breakouts)

    # 4. Expire stale alerts
    expire_old_alerts()

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
