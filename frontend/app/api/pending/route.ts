import { NextRequest, NextResponse } from "next/server";
import { queryAll, execute } from "@/lib/db";

export async function GET() {
  try {
    const pending = await queryAll<{
      id: number;
      keyword: string;
      suggested_category: string;
      source: string;
      parent_keyword: string;
      relevance_score: number;
      discovered_at: string;
      status: string;
    }>(
      `SELECT id, keyword, suggested_category, source, parent_keyword,
              relevance_score, discovered_at, status
       FROM pending_keywords
       WHERE status = 'pending'
       ORDER BY relevance_score DESC, discovered_at DESC`
    );

    return NextResponse.json({ pending });
  } catch (error) {
    console.error("Pending keywords API error:", error);
    return NextResponse.json({ error: "Failed to fetch pending keywords", pending: [] }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { id, action } = body;

    if (!id || !action) {
      return NextResponse.json({ error: "id and action are required" }, { status: 400 });
    }

    if (action === "approve") {
      // Get the pending keyword
      const pending = await queryAll<{
        keyword: string;
        suggested_category: string;
        source: string;
        parent_keyword: string;
      }>("SELECT keyword, suggested_category, source, parent_keyword FROM pending_keywords WHERE id = ?", [id]);

      if (pending.length === 0) {
        return NextResponse.json({ error: "Pending keyword not found" }, { status: 404 });
      }

      const { keyword, suggested_category, source, parent_keyword } = pending[0];

      // Insert into keywords table
      await execute(
        `INSERT INTO keywords (keyword, category, is_active)
         VALUES (?, ?, 1)
         ON CONFLICT(keyword) DO UPDATE SET is_active = 1, category = excluded.category`,
        [keyword, suggested_category]
      );

      // Ensure category exists
      await execute(
        `INSERT INTO categories (name, is_active) VALUES (?, 1)
         ON CONFLICT(name) DO NOTHING`,
        [suggested_category]
      );

      // Mark as approved
      await execute("UPDATE pending_keywords SET status = 'approved' WHERE id = ?", [id]);

      // Record feedback for discovery loop
      const feedbackSource = source || 'unknown';
      const feedbackParent = parent_keyword || '';
      await execute(`
        INSERT INTO discovery_stats (source, parent_keyword, total_suggested, total_approved, total_rejected, approval_rate, last_updated)
        VALUES (?, ?, 1, 1, 0, 1.0, datetime('now'))
        ON CONFLICT(source, parent_keyword) DO UPDATE SET
            total_suggested = total_suggested + 1,
            total_approved = total_approved + 1,
            approval_rate = CAST(total_approved + 1 AS REAL) / CAST(total_suggested + 1 AS REAL),
            last_updated = datetime('now')
      `, [feedbackSource, feedbackParent]);
    } else if (action === "reject") {
      // Get source info before marking as rejected
      const pending = await queryAll<{
        source: string;
        parent_keyword: string;
      }>("SELECT source, parent_keyword FROM pending_keywords WHERE id = ?", [id]);

      await execute("UPDATE pending_keywords SET status = 'rejected' WHERE id = ?", [id]);

      // Record feedback for discovery loop
      if (pending.length > 0) {
        const feedbackSource = pending[0].source || 'unknown';
        const feedbackParent = pending[0].parent_keyword || '';
        await execute(`
          INSERT INTO discovery_stats (source, parent_keyword, total_suggested, total_approved, total_rejected, approval_rate, last_updated)
          VALUES (?, ?, 1, 0, 1, 0.0, datetime('now'))
          ON CONFLICT(source, parent_keyword) DO UPDATE SET
              total_suggested = total_suggested + 1,
              total_rejected = total_rejected + 1,
              approval_rate = CAST(total_approved AS REAL) / CAST(total_suggested + 1 AS REAL),
              last_updated = datetime('now')
        `, [feedbackSource, feedbackParent]);
      }
    } else {
      return NextResponse.json({ error: "Action must be 'approve' or 'reject'" }, { status: 400 });
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Pending keyword action error:", error);
    return NextResponse.json({ error: "Failed to process pending keyword" }, { status: 500 });
  }
}
