"""Auto-triage for the pending_keywords queue.

History showed the manual approval gate was a rubber stamp (13k approvals,
zero rejections), so this module is the real quality gate:

  auto-reject  — junk (filter rules improved since insertion), relevance
                 below the floor, or stale (pending > 30 days)
  auto-approve — relevance at/above the bar AND not junk, capped per
                 category per run, and ONLY for categories below the
                 max share of active keywords (beauty at 67% gets no
                 auto-approvals — manual review only)
  middle band  — left pending for human review

Statuses written: 'auto_rejected' / 'auto_approved' so they are
distinguishable from manual decisions. discovery_stats is updated the
same way the dashboard approve/reject endpoints do.
"""

import sqlite3
import logging
from datetime import datetime

from config import DB_PATH, TRIAGE
from keyword_filter import is_junk

logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _record_feedback(cursor, source: str, parent: str, approved: bool):
    """Update discovery_stats the same way the dashboard endpoints do."""
    cursor.execute(
        """INSERT INTO discovery_stats
               (source, parent_keyword, total_suggested, total_approved,
                total_rejected, approval_rate, last_updated)
           VALUES (?, ?, 1, ?, ?, ?, datetime('now'))
           ON CONFLICT(source, parent_keyword) DO UPDATE SET
               total_suggested = total_suggested + 1,
               total_approved = total_approved + excluded.total_approved,
               total_rejected = total_rejected + excluded.total_rejected,
               approval_rate = CAST(total_approved + excluded.total_approved AS REAL)
                               / CAST(total_suggested + 1 AS REAL),
               last_updated = datetime('now')""",
        (
            source or "unknown",
            parent or "",
            1 if approved else 0,
            0 if approved else 1,
            1.0 if approved else 0.0,
        ),
    )


def _category_shares(cursor) -> dict:
    """Share of active keywords held by each category."""
    cursor.execute(
        "SELECT category, COUNT(*) AS cnt FROM keywords WHERE is_active = 1 GROUP BY category"
    )
    rows = cursor.fetchall()
    total = sum(r["cnt"] for r in rows) or 1
    return {r["category"]: r["cnt"] / total for r in rows}


def sweep_active_junk(days: int | None = 14, apply: bool = True) -> int:
    """Find or deactivate high-confidence junk among active keywords.

    The scheduled safety sweep keeps its conservative 14-day default. Passing
    ``days=None`` audits the entire active watchlist, and ``apply=False`` makes
    that audit read-only so historical cleanup can be reviewed before use.
    Returns the number of rows matching the current high-confidence junk rules.
    """
    db = get_db()
    if days is None:
        rows = db.execute(
            "SELECT id, keyword FROM keywords WHERE is_active = 1"
        ).fetchall()
        scope = "all-history"
    else:
        rows = db.execute(
            "SELECT id, keyword FROM keywords WHERE is_active = 1 "
            "AND added_at >= datetime('now', ?)",
            (f"-{int(days)} days",),
        ).fetchall()
        scope = f"last-{int(days)}-days"

    junk_ids = [(row["id"],) for row in rows if is_junk(row["keyword"])[0]]
    if apply and junk_ids:
        db.executemany("UPDATE keywords SET is_active = 0 WHERE id = ?", junk_ids)
        db.commit()

    action = "deactivated" if apply else "would deactivate"
    logger.info(
        "Active-junk sweep (%s): %s %d of %d active keywords",
        scope,
        action,
        len(junk_ids),
        len(rows),
    )
    db.close()
    return len(junk_ids)


def triage_pending():
    """Run one triage pass over status='pending' keywords, plus a junk sweep
    of recently-added active keywords (bulk imports bypass the filter).

    Returns (success: bool, items_actioned: int, error: str | None).
    Never raises to the scheduler.
    """
    try:
        swept = sweep_active_junk()

        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            """SELECT id, keyword, suggested_category, source, parent_keyword,
                      relevance_score, discovered_at
               FROM pending_keywords WHERE status = 'pending'
               ORDER BY relevance_score DESC"""
        )
        pending = cursor.fetchall()
        if not pending:
            db.close()
            logger.info("Triage: queue is empty.")
            if swept:
                return (True, swept, None)
            # Skip reason (not None) so the stall guard doesn't treat a
            # healthy empty queue as a silently-broken collector.
            return (True, 0, "queue empty")

        shares = _category_shares(cursor)
        max_share = TRIAGE["max_category_share"]
        approve_caps = {}  # category -> approvals granted this run

        rejected = {"junk": 0, "low_relevance": 0, "stale": 0}
        approved = 0
        stale_cutoff = f"-{int(TRIAGE['stale_days'])} days"
        cursor.execute("SELECT datetime('now', ?)", (stale_cutoff,))
        stale_before = cursor.fetchone()[0]

        def _reject(row, reason):
            cursor.execute(
                "UPDATE pending_keywords SET status = 'auto_rejected' WHERE id = ?",
                (row["id"],),
            )
            _record_feedback(cursor, row["source"], row["parent_keyword"], approved=False)
            rejected[reason] += 1

        for row in pending:
            relevance = row["relevance_score"] or 0
            category = row["suggested_category"]

            junk, _ = is_junk(row["keyword"])
            if junk:
                _reject(row, "junk")
                continue

            # Owner bulk imports: deliberate lists, so once past the junk
            # filter they're approved unconditionally — no share cap, no
            # relevance bar, honoring the owner's category (+ subcategory,
            # carried in parent_keyword by the import routes).
            if row["source"] == "bulk_import":
                cursor.execute(
                    """INSERT INTO keywords (keyword, category, subcategory, is_active)
                       VALUES (?, ?, NULLIF(?, ''), 1)
                       ON CONFLICT(keyword) DO UPDATE SET
                           category = excluded.category,
                           subcategory = COALESCE(excluded.subcategory, keywords.subcategory),
                           is_active = 1""",
                    (row["keyword"], category, row["parent_keyword"] or ""),
                )
                cursor.execute(
                    """INSERT INTO categories (name, is_active) VALUES (?, 1)
                       ON CONFLICT(name) DO NOTHING""",
                    (category,),
                )
                cursor.execute(
                    "UPDATE pending_keywords SET status = 'auto_approved' WHERE id = ?",
                    (row["id"],),
                )
                approved += 1
                continue

            if relevance < TRIAGE["auto_reject_relevance"]:
                _reject(row, "low_relevance")
                continue

            # Approve-eligibility comes before staleness so a strong keyword
            # that aged in the queue is still approved, not swept out.
            if (
                relevance >= TRIAGE["auto_approve_relevance"]
                and shares.get(category, 0) <= max_share
                and approve_caps.get(category, 0) < TRIAGE["max_auto_approvals_per_category"]
            ):
                cursor.execute(
                    """INSERT INTO keywords (keyword, category, is_active)
                       VALUES (?, ?, 1)
                       ON CONFLICT(keyword) DO UPDATE SET is_active = 1""",
                    (row["keyword"], category),
                )
                cursor.execute(
                    """INSERT INTO categories (name, is_active) VALUES (?, 1)
                       ON CONFLICT(name) DO NOTHING""",
                    (category,),
                )
                cursor.execute(
                    "UPDATE pending_keywords SET status = 'auto_approved' WHERE id = ?",
                    (row["id"],),
                )
                _record_feedback(cursor, row["source"], row["parent_keyword"], approved=True)
                approve_caps[category] = approve_caps.get(category, 0) + 1
                approved += 1
                continue

            # Nobody (human or machine) wanted it within the window: clear it
            if (row["discovered_at"] or "") < stale_before:
                _reject(row, "stale")

        db.commit()
        remaining = db.execute(
            "SELECT COUNT(*) FROM pending_keywords WHERE status = 'pending'"
        ).fetchone()[0]
        db.close()

        total_rejected = sum(rejected.values())
        logger.info(
            f"Triage: approved {approved}, rejected {total_rejected} "
            f"(junk={rejected['junk']}, low_relevance={rejected['low_relevance']}, "
            f"stale={rejected['stale']}), {remaining} left for human review."
        )
        return (True, approved + total_rejected + swept, None)
    except Exception as e:
        logger.error(f"Triage failed: {e}", exc_info=True)
        return (False, 0, str(e))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success, actioned, err = triage_pending()
    print(f"Triage: success={success} actioned={actioned} error={err}")
