import { NextRequest, NextResponse } from "next/server";
import { queryAll, execute } from "@/lib/db";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const rising = searchParams.get("rising") === "true";
  const limit = parseInt(searchParams.get("limit") || "20", 10);

  try {
    // Get keywords with latest trend data and calculated velocity
    const rows = await queryAll<{
      keyword: string;
      category: string;
      current_score: number;
      prev_score: number;
    }>(
      `SELECT k.keyword, k.category,
              td_current.interest_score as current_score,
              COALESCE(td_prev.interest_score, 1) as prev_score
       FROM keywords k
       LEFT JOIN (
         SELECT keyword_id, interest_score,
                ROW_NUMBER() OVER (PARTITION BY keyword_id ORDER BY date DESC) as rn
         FROM trend_data
       ) td_current ON k.id = td_current.keyword_id AND td_current.rn = 1
       LEFT JOIN (
         SELECT keyword_id, interest_score,
                ROW_NUMBER() OVER (PARTITION BY keyword_id ORDER BY date DESC) as rn
         FROM trend_data
         WHERE date <= date('now', '-28 days')
       ) td_prev ON k.id = td_prev.keyword_id AND td_prev.rn = 1
       WHERE k.is_active = 1
         AND td_current.interest_score IS NOT NULL`
    );

    const keywords = rows.map((row) => {
      const change =
        row.prev_score > 0
          ? Math.round(((row.current_score / row.prev_score) * 100 - 100) * 10) / 10
          : 0;
      return {
        keyword: row.keyword,
        category: row.category,
        interest_score: row.current_score,
        change_pct: change,
      };
    });

    if (rising) {
      keywords.sort((a, b) => b.change_pct - a.change_pct);
    } else {
      keywords.sort((a, b) => b.interest_score - a.interest_score);
    }

    // Also get recent alerts
    const alerts = await queryAll<{
      id: number;
      type: string;
      severity: string;
      message: string;
      data: string;
      sent_at: string;
    }>(
      `SELECT id, type, severity, message, data, sent_at
       FROM alerts
       WHERE sent_at >= datetime('now', '-7 days')
       ORDER BY sent_at DESC
       LIMIT 20`
    );

    const parsedAlerts = alerts.map((a) => ({
      ...a,
      data: (() => {
        try {
          return JSON.parse(a.data || "{}");
        } catch {
          return {};
        }
      })(),
    }));

    return NextResponse.json({
      keywords: keywords.slice(0, limit),
      alerts: parsedAlerts,
    });
  } catch (error) {
    console.error("Keywords API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch keywords", keywords: [], alerts: [] },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { keyword, category, subcategory } = body;

    if (!keyword || !category) {
      return NextResponse.json({ error: "keyword and category are required" }, { status: 400 });
    }

    // Ensure category exists
    await execute(
      `INSERT INTO categories (name, is_active) VALUES (?, 1)
       ON CONFLICT(name) DO NOTHING`,
      [category.toLowerCase()]
    );

    await execute(
      `INSERT INTO keywords (keyword, category, subcategory, is_active)
       VALUES (?, ?, ?, 1)
       ON CONFLICT(keyword) DO UPDATE SET
         category = excluded.category,
         subcategory = excluded.subcategory,
         is_active = 1`,
      [keyword.toLowerCase(), category.toLowerCase(), subcategory || null]
    );

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Add keyword error:", error);
    return NextResponse.json({ error: "Failed to add keyword" }, { status: 500 });
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const { keyword, is_active } = body;

    if (!keyword) {
      return NextResponse.json({ error: "keyword is required" }, { status: 400 });
    }

    await execute(
      "UPDATE keywords SET is_active = ? WHERE keyword = ?",
      [is_active ? 1 : 0, keyword]
    );

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Update keyword error:", error);
    return NextResponse.json({ error: "Failed to update keyword" }, { status: 500 });
  }
}
