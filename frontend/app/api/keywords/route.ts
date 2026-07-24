import { NextRequest, NextResponse } from "next/server";
import { queryAll, queryOne, execute } from "@/lib/db";

function boundedInt(value: string | null, fallback: number, minimum: number, maximum: number): number {
  const parsed = Number.parseInt(value || "", 10);
  return Number.isFinite(parsed) ? Math.min(Math.max(parsed, minimum), maximum) : fallback;
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const rising = searchParams.get("rising") === "true";
  const limit = boundedInt(searchParams.get("limit"), 20, 1, 100);
  const admin = searchParams.get("admin") === "true";

  try {
    if (admin) {
      const page = boundedInt(searchParams.get("page"), 1, 1, 1_000_000);
      const pageSize = boundedInt(searchParams.get("page_size"), 100, 1, 200);
      const search = (searchParams.get("search") || "").trim().toLowerCase();
      const category = (searchParams.get("category") || "").trim().toLowerCase();
      const where: string[] = [];
      const params: unknown[] = [];

      if (search) {
        where.push("(LOWER(keyword) LIKE ? OR LOWER(category) LIKE ? OR LOWER(COALESCE(subcategory, '')) LIKE ?)");
        const term = `%${search}%`;
        params.push(term, term, term);
      }
      if (category) {
        where.push("category = ?");
        params.push(category);
      }

      const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";
      const count = await queryOne<{ cnt: number }>(
        `SELECT COUNT(*) AS cnt FROM keywords ${whereSql}`,
        params,
      );
      const total = count?.cnt || 0;
      const totalPages = Math.max(Math.ceil(total / pageSize), 1);
      const safePage = Math.min(page, totalPages);
      const offset = (safePage - 1) * pageSize;
      const rows = await queryAll<{
        id: number;
        keyword: string;
        category: string;
        subcategory: string | null;
        is_active: number;
      }>(
        `SELECT id, keyword, category, subcategory, is_active
         FROM keywords
         ${whereSql}
         ORDER BY category, keyword
         LIMIT ? OFFSET ?`,
        [...params, pageSize, offset],
      );

      return NextResponse.json({
        keywords: rows.map((row) => ({ ...row, is_active: row.is_active === 1 })),
        pagination: {
          page: safePage,
          page_size: pageSize,
          total,
          total_pages: totalPages,
        },
      });
    }

    // Get keywords with latest trend data and analyzer-computed velocity
    const rows = await queryAll<{
      keyword: string;
      category: string;
      current_score: number;
      prev_score: number;
      velocity_4w: number | null;
      velocity_yoy: number | null;
      is_seasonal: number | null;
      lifecycle: string | null;
    }>(
      `SELECT k.keyword, k.category,
              td_current.interest_score as current_score,
              COALESCE(td_prev.interest_score, 1) as prev_score,
              km.velocity_4w, km.velocity_yoy, km.is_seasonal, km.lifecycle
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
       LEFT JOIN keyword_metrics km ON k.id = km.keyword_id
       WHERE k.is_active = 1
         AND td_current.interest_score IS NOT NULL`
    );

    const keywords = rows.map((row) => {
      // Prefer the analyzer's window-averaged velocity; fall back to the
      // single-point calculation for keywords it has not covered yet.
      const fallback =
        row.prev_score > 0
          ? Math.round(((row.current_score / row.prev_score) * 100 - 100) * 10) / 10
          : 0;
      return {
        keyword: row.keyword,
        category: row.category,
        interest_score: row.current_score,
        change_pct: row.velocity_4w ?? fallback,
        velocity_yoy: row.velocity_yoy,
        is_seasonal: row.is_seasonal === 1,
        lifecycle: row.lifecycle ?? "stable",
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
