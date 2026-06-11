import { NextRequest, NextResponse } from "next/server";
import { queryAll } from "@/lib/db";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const category = searchParams.get("category");
  const days = parseInt(searchParams.get("days") || "90", 10);

  try {
    let sql = `
      SELECT k.keyword, k.category, k.subcategory, td.date, td.interest_score,
             td.related_rising, td.region_data
      FROM trend_data td
      JOIN keywords k ON td.keyword_id = k.id
      WHERE td.date >= date('now', '-' || ? || ' days')
        AND k.is_active = 1
    `;
    const params: unknown[] = [days];

    if (category) {
      sql += " AND k.category = ?";
      params.push(category);
    }

    sql += " ORDER BY td.date DESC, td.interest_score DESC";

    const rows = await queryAll<{
      keyword: string;
      category: string;
      subcategory: string | null;
      date: string;
      interest_score: number;
      related_rising: string | null;
      region_data: string | null;
    }>(sql, params);

    // Group by keyword with velocity calculation
    const keywordMap = new Map<
      string,
      {
        keyword: string;
        category: string;
        subcategory: string | null;
        history: { date: string; interest_score: number }[];
        related_rising: string[];
        region_data: Record<string, number>;
      }
    >();

    for (const row of rows) {
      if (!keywordMap.has(row.keyword)) {
        keywordMap.set(row.keyword, {
          keyword: row.keyword,
          category: row.category,
          subcategory: row.subcategory || null,
          history: [],
          related_rising: [],
          region_data: {},
        });
      }
      const entry = keywordMap.get(row.keyword)!;
      entry.history.push({
        date: row.date,
        interest_score: row.interest_score,
      });

      if (row.related_rising && entry.related_rising.length === 0) {
        try {
          entry.related_rising = JSON.parse(row.related_rising);
        } catch {
          // ignore parse errors
        }
      }
      if (row.region_data && Object.keys(entry.region_data).length === 0) {
        try {
          entry.region_data = JSON.parse(row.region_data);
        } catch {
          // ignore parse errors
        }
      }
    }

    // Analyzer-computed metrics (window-averaged velocities, YoY,
    // seasonality, lifecycle) — the same numbers alerts are based on.
    const metricRows = await queryAll<{
      keyword: string;
      velocity_4w: number;
      velocity_12w: number;
      velocity_yoy: number | null;
      is_seasonal: number;
      lifecycle: string | null;
    }>(
      `SELECT k.keyword, km.velocity_4w, km.velocity_12w, km.velocity_yoy,
              km.is_seasonal, km.lifecycle
       FROM keyword_metrics km
       JOIN keywords k ON k.id = km.keyword_id
       WHERE k.is_active = 1`
    ).catch(() => [] as never[]); // table may not exist before migration 004
    const metricMap = new Map(metricRows.map((m) => [m.keyword, m]));

    const trends = Array.from(keywordMap.values()).map((entry) => {
      const sorted = entry.history.sort(
        (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
      );
      const current = sorted[0]?.interest_score || 0;
      const metrics = metricMap.get(entry.keyword);

      // Fallback to the old single-point math only when the analyzer
      // has not computed metrics for this keyword yet.
      const fourWeeks = sorted[3]?.interest_score || sorted[sorted.length - 1]?.interest_score || 1;
      const twelveWeeks = sorted[11]?.interest_score || sorted[sorted.length - 1]?.interest_score || 1;

      return {
        ...entry,
        current_interest: current,
        velocity_4w:
          metrics?.velocity_4w ??
          Math.round(((current / Math.max(fourWeeks, 1)) * 100 - 100) * 10) / 10,
        velocity_12w:
          metrics?.velocity_12w ??
          Math.round(((current / Math.max(twelveWeeks, 1)) * 100 - 100) * 10) / 10,
        velocity_yoy: metrics?.velocity_yoy ?? null,
        is_seasonal: metrics ? metrics.is_seasonal === 1 : false,
        lifecycle: metrics?.lifecycle ?? "stable",
      };
    });

    // Sort by velocity
    trends.sort((a, b) => b.velocity_4w - a.velocity_4w);

    // Also get niche scores
    const scoreRows = await queryAll<{
      category: string;
      overall_score: number;
      trend_score: number;
      margin_score: number;
      competition_score: number;
      sourcing_score: number;
      content_score: number;
      repeat_purchase_score: number;
      provenance: string | null;
    }>(
      `SELECT * FROM niche_scores
       WHERE date = (SELECT MAX(date) FROM niche_scores)
       ORDER BY overall_score DESC`
    );

    const scores = scoreRows.map((s) => ({
      ...s,
      // {"trend": "real" | "fallback", ...} — which components come from
      // collected data vs hardcoded category defaults
      provenance: (() => {
        try {
          return s.provenance ? JSON.parse(s.provenance) : null;
        } catch {
          return null;
        }
      })(),
    }));

    return NextResponse.json({ trends, scores });
  } catch (error) {
    console.error("Trends API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch trends", trends: [], scores: [] },
      { status: 500 }
    );
  }
}
