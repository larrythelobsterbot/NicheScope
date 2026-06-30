"""Dead-keyword pruning.

Deactivates keywords nobody searches for anymore so they stop consuming the
Google Trends collection budget. "Dead" is deliberately conservative:

  - tracked for at least PRUNE["min_age_days"] (newcomers get time to develop)
  - peak interest over the last PRUNE["window_days"] is below PRUNE["max_peak"]
  - has at least PRUNE["min_points"] data points (we actually measured it)

Keywords are DEACTIVATED (is_active = 0), never deleted: trend history is kept,
and if discovery or a manual add surfaces a keyword again the existing upsert
paths flip is_active back to 1 automatically.

Runs weekly from the scheduler; also exposed as a CLI via
scripts/prune_keywords.py.
"""

import logging
import sqlite3

from config import DB_PATH, PRUNE

logger = logging.getLogger(__name__)


def _dead_keywords_sql(window_days: int, min_age_days: int, min_points: int) -> str:
    return f"""
        SELECT k.id, k.keyword, k.category
        FROM keywords k
        JOIN trend_data td ON td.keyword_id = k.id
            AND td.date >= date('now', '-{int(window_days)} days')
        WHERE k.is_active = 1
          AND (SELECT MIN(date) FROM trend_data WHERE keyword_id = k.id)
                  <= date('now', '-{int(min_age_days)} days')
        GROUP BY k.id
        HAVING MAX(td.interest_score) < :max_peak
           AND COUNT(td.id) >= {int(min_points)}
    """


def find_dead_keywords(conn, max_peak=None):
    """Return a list of (id, keyword, category) for keywords that are dead."""
    max_peak = PRUNE["max_peak"] if max_peak is None else max_peak
    sql = _dead_keywords_sql(PRUNE["window_days"], PRUNE["min_age_days"], PRUNE["min_points"])
    return conn.execute(sql, {"max_peak": max_peak}).fetchall()


def prune_dead_keywords(apply=True, max_peak=None):
    """Deactivate dead keywords.

    Returns (success: bool, count: int, error: str | None) to match the
    collector-job contract. Never raises to the scheduler.
    """
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        dead = find_dead_keywords(conn, max_peak=max_peak)

        if not apply:
            conn.close()
            # Skip reason (not None) so the stall guard ignores a dry run.
            return (True, len(dead), "dry-run")

        if dead:
            conn.executemany(
                "UPDATE keywords SET is_active = 0 WHERE id = ?",
                [(r["id"],) for r in dead],
            )
            conn.commit()
        remaining = conn.execute(
            "SELECT COUNT(*) FROM keywords WHERE is_active = 1"
        ).fetchone()[0]
        conn.close()

        logger.info(
            f"Prune: deactivated {len(dead)} dead keywords; {remaining} remain active."
        )
        return (True, len(dead), None)
    except Exception as e:
        logger.error(f"Prune failed: {e}", exc_info=True)
        return (False, 0, str(e))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success, count, err = prune_dead_keywords(apply=True)
    print(f"Prune: success={success} deactivated={count} error={err}")
