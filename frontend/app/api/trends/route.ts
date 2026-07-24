import { NextRequest, NextResponse } from "next/server";
import { queryAll, queryOne } from "@/lib/db";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const DEFAULT_TREND_KEYWORDS = 500;
const MAX_TREND_KEYWORDS = 1000;

function boundedInt(value: string | null, fallback: number, minimum: number, maximum: number): number {
  const parsed = Number.parseInt(value || "", 10);
  return Number.isFinite(parsed) ? Math.min(Math.max(parsed, minimum), maximum) : fallback;
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const category = searchParams.get("category")?.trim() || null;
  const days = boundedInt(searchParams.get("days"), 90, 7, 730);
  const keywordLimit = boundedInt(
    searchParams.get("keyword_limit"),
    DEFAULT_TREND_KEYWORDS,
    1,
    MAX_TREND_KEYWORDS,
  );

  try {
    const categoryClause = category ? "AND k.category = ?" : "";
    const countParams: unknown[] = [days];
    if (category) countParams.push(category);

    const available = await queryOne<{ cnt: number }>(
      `SELECT COUNT(*) AS cnt
       FROM keywords k
       WHERE k.is_active = 1
         AND EXISTS (
           SELECT 1 FROM trend_data recent
           WHERE recent.keyword_id = k.id
             AND recent.date >= date('now', '-' || ? || ' days')
         )
         ${categoryClause}`,
      countParams,
    );

    const params: unknown[] = [days];
    if (category) params.push(category);
    params.push(keywordLimit, days);

    const rows = await queryAll<{
      keyword: string;
      category: string;
      subcategory: string | null;
      date: string;
      interest_score: number;
      related_rising: string | null;
      region_data: string | null;
    }>(
      `WITH selected_keywords AS (
         SELECT k.id
         FROM keywords k
         LEFT JOIN keyword_metrics km ON km.keyword_id = k.id
         WHERE k.is_active = 1
           AND EXISTS (
             SELECT 1 FROM trend_data recent
             WHERE recent.keyword_id = k.id
               AND recent.date >= date('now', '-' || ? || ' days')
           )
           ${categoryClause}
         ORDER BY
           CASE km.lifecycle
             WHEN 'emerging' THEN 0
             WHEN 'accelerating' THEN 1
             WHEN 'peaking' THEN 2
             ELSE 3
           END,
           ABS(COALESCE(km.velocity_4w, 0)) DESC,
           k.id DESC
         LIMIT ?
       )
       SELECT k.keyword, k.category, k.subcategory, td.date, td.interest_score,
              td.related_rising, td.region_data
       FROM trend_data td
       JOIN selected_keywords selected ON selected.id = td.keyword_id
       JOIN keywords k ON td.keyword_id = k.id
       WHERE td.date >= date('now', '-' || ? || ' days')
       ORDER BY td.date DESC, td.interest_score DESC`,
      params,
    );

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
      entry.history.push({ date: row.date, interest_score: row.interest_score });

      if (row.related_rising && entry.related_rising.length === 0) {
        try {
          entry.related_rising = JSON.parse(row.related_rising);
        } catch {
          // Ignore malformed collector metadata; trend history remains usable.
        }
      }
      if (row.region_data && Object.keys(entry.region_data).length === 0) {
        try {
          entry.region_data = JSON.parse(row.region_data);
        } catch {
          // Ignore malformed collector metadata; trend history remains usable.
        }
      }
    }

    const selectedKeywords = Array.from(keywordMap.keys());
    const metricRows = selectedKeywords.length
      ? await queryAll<{
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
           WHERE k.keyword IN (${selectedKeywords.map(() => "?").join(",")})`,
          selectedKeywords,
        ).catch(() => [] as never[])
      : [];
    const metricMap = new Map(metricRows.map((metric) => [metric.keyword, metric]));

    const trends = Array.from(keywordMap.values()).map((entry) => {
      const sorted = entry.history.sort(
        (left, right) => new Date(right.date).getTime() - new Date(left.date).getTime(),
      );
      const current = sorted[0]?.interest_score || 0;
      const metrics = metricMap.get(entry.keyword);
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

    trends.sort((left, right) => right.velocity_4w - left.velocity_4w);

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
       ORDER BY overall_score DESC`,
    );

    const scores = scoreRows.map((score) => ({
      ...score,
      provenance: (() => {
        try {
          return score.provenance ? JSON.parse(score.provenance) : null;
        } catch {
          return null;
        }
      })(),
    }));

    const availableKeywords = available?.cnt || 0;
    return NextResponse.json(
      {
        trends,
        scores,
        meta: {
          available_keywords: availableKeywords,
          returned_keywords: trends.length,
          keyword_limit: keywordLimit,
          truncated: availableKeywords > trends.length,
        },
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    console.error("Trends API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch trends", trends: [], scores: [] },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
