"""
NicheScope Discovery Feedback Loop
=====================================
Tracks which discovery sources and parent keywords produce the most
approved vs rejected keywords. Uses this data to weight future
discovery runs — productive sources get more attention, low-quality
sources get deprioritized.

Schema (added to init_db.py):
    discovery_stats:
        source TEXT (e.g., 'google_category', 'google_related', 'reddit', 'etsy')
        parent_keyword TEXT
        total_suggested INTEGER
        total_approved INTEGER
        total_rejected INTEGER
        approval_rate REAL (computed)
        last_updated DATETIME
"""

import sqlite3
import logging
from datetime import datetime
from config import DB_PATH

logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def record_keyword_decision(keyword: str, decision: str):
    """
    Called when a user approves or rejects a pending keyword.
    Updates the discovery_stats table to track source effectiveness.

    Args:
        keyword: The keyword that was approved/rejected
        decision: 'approved' or 'rejected'
    """
    db = get_db()
    try:
        # Get the source and parent_keyword for this pending keyword
        row = db.execute(
            "SELECT source, parent_keyword FROM pending_keywords WHERE keyword = ?",
            (keyword,)
        ).fetchone()

        if not row:
            logger.debug(f"No pending keyword found for '{keyword}'")
            return

        source = row["source"] or "unknown"
        parent = row["parent_keyword"] or ""
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        if decision == "approved":
            db.execute("""
                INSERT INTO discovery_stats (source, parent_keyword, total_suggested, total_approved, total_rejected, approval_rate, last_updated)
                VALUES (?, ?, 1, 1, 0, 1.0, ?)
                ON CONFLICT(source, parent_keyword) DO UPDATE SET
                    total_suggested = total_suggested + 1,
                    total_approved = total_approved + 1,
                    approval_rate = CAST(total_approved + 1 AS REAL) / CAST(total_suggested + 1 AS REAL),
                    last_updated = ?
            """, (source, parent, now, now))
        elif decision == "rejected":
            db.execute("""
                INSERT INTO discovery_stats (source, parent_keyword, total_suggested, total_approved, total_rejected, approval_rate, last_updated)
                VALUES (?, ?, 1, 0, 1, 0.0, ?)
                ON CONFLICT(source, parent_keyword) DO UPDATE SET
                    total_suggested = total_suggested + 1,
                    total_rejected = total_rejected + 1,
                    approval_rate = CAST(total_approved AS REAL) / CAST(total_suggested + 1 AS REAL),
                    last_updated = ?
            """, (source, parent, now, now))

        db.commit()
        logger.info(f"Recorded {decision} for '{keyword}' (source={source}, parent={parent})")
    except Exception as e:
        logger.error(f"Failed to record feedback for '{keyword}': {e}")
    finally:
        db.close()


def get_source_weights() -> dict:
    """
    Calculate discovery source weights based on historical approval rates.
    Returns a dict of source -> weight (0.0 to 2.0).

    Weight logic:
    - Sources with >60% approval rate get weight 1.5-2.0 (more discovery effort)
    - Sources with 30-60% approval rate get weight 1.0 (normal)
    - Sources with <30% approval rate get weight 0.3-0.7 (less effort)
    - New sources with <5 decisions get weight 1.0 (neutral until proven)
    """
    db = get_db()
    try:
        rows = db.execute("""
            SELECT source,
                   SUM(total_approved) as approved,
                   SUM(total_rejected) as rejected,
                   SUM(total_suggested) as total
            FROM discovery_stats
            GROUP BY source
        """).fetchall()

        weights = {}
        for row in rows:
            total = row["total"] or 0
            approved = row["approved"] or 0

            if total < 5:
                weights[row["source"]] = 1.0  # Not enough data
                continue

            rate = approved / total if total > 0 else 0

            if rate > 0.6:
                weights[row["source"]] = 1.5 + (rate - 0.6) * 1.25  # 1.5 to 2.0
            elif rate > 0.3:
                weights[row["source"]] = 1.0
            else:
                weights[row["source"]] = max(0.3, rate * 2.33)  # 0.3 to 0.7

        return weights
    except Exception as e:
        logger.error(f"Failed to get source weights: {e}")
        return {}
    finally:
        db.close()


def get_productive_parents(source: str, limit: int = 20) -> list:
    """
    Get the most productive parent keywords for a given source.
    These are parents whose discovered keywords have high approval rates.
    """
    db = get_db()
    try:
        rows = db.execute("""
            SELECT parent_keyword, total_approved, total_suggested, approval_rate
            FROM discovery_stats
            WHERE source = ? AND total_suggested >= 3
            ORDER BY approval_rate DESC, total_approved DESC
            LIMIT ?
        """, (source, limit)).fetchall()

        return [
            {
                "parent": row["parent_keyword"],
                "approved": row["total_approved"],
                "total": row["total_suggested"],
                "rate": row["approval_rate"],
            }
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Failed to get productive parents: {e}")
        return []
    finally:
        db.close()


def should_skip_source(source: str) -> bool:
    """
    Returns True if a source has consistently low approval rates
    and should be skipped this run to save API calls.

    Only skips if:
    - Source has 20+ decisions (enough data)
    - Approval rate is below 10%
    """
    weights = get_source_weights()
    weight = weights.get(source)

    if weight is None:
        return False  # Unknown source, don't skip

    return weight < 0.3


def get_discovery_report() -> dict:
    """
    Generate a summary report of discovery source effectiveness.
    Used for the admin panel and Telegram digest.
    """
    db = get_db()
    try:
        rows = db.execute("""
            SELECT source,
                   SUM(total_approved) as approved,
                   SUM(total_rejected) as rejected,
                   SUM(total_suggested) as total,
                   MAX(last_updated) as last_active
            FROM discovery_stats
            GROUP BY source
            ORDER BY SUM(total_approved) DESC
        """).fetchall()

        report = {
            "sources": [],
            "total_approved": 0,
            "total_rejected": 0,
        }

        for row in rows:
            total = row["total"] or 0
            approved = row["approved"] or 0
            rejected = row["rejected"] or 0
            rate = approved / total if total > 0 else 0

            report["sources"].append({
                "source": row["source"],
                "approved": approved,
                "rejected": rejected,
                "total": total,
                "approval_rate": round(rate * 100, 1),
                "last_active": row["last_active"],
            })
            report["total_approved"] += approved
            report["total_rejected"] += rejected

        # Top productive parents across all sources
        top_parents = db.execute("""
            SELECT source, parent_keyword, total_approved, approval_rate
            FROM discovery_stats
            WHERE total_suggested >= 3
            ORDER BY total_approved DESC
            LIMIT 10
        """).fetchall()

        report["top_parents"] = [
            {
                "source": r["source"],
                "parent": r["parent_keyword"],
                "approved": r["total_approved"],
                "rate": round((r["approval_rate"] or 0) * 100, 1),
            }
            for r in top_parents
        ]

        return report
    except Exception as e:
        logger.error(f"Failed to generate discovery report: {e}")
        return {"sources": [], "total_approved": 0, "total_rejected": 0, "top_parents": []}
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    report = get_discovery_report()
    print("\nDiscovery Source Report:")
    for s in report["sources"]:
        print(f"  {s['source']}: {s['approved']}/{s['total']} approved ({s['approval_rate']}%)")
    print(f"\nTop Productive Parents:")
    for p in report["top_parents"]:
        print(f"  [{p['source']}] '{p['parent']}': {p['approved']} approved ({p['rate']}%)")
