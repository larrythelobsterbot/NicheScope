import { NextResponse } from "next/server";
import { queryAll, queryOne } from "@/lib/db";

// Decision-focused metrics for the dashboard command center: what's emerging,
// what's the single best opportunity, where the watchlist lives, how much of
// the scoring is real vs fallback. All computed from keyword_metrics +
// niche_scores so the dashboard surfaces verdicts, not raw counts.

// Categories that are over-represented / not e-commerce niches we'd build on.
const DEEMPHASISED = new Set(["beauty", "general"]);

export async function GET() {
  try {
    // ─── Lifecycle distribution across the active watchlist ───
    const lifecycleRows = await queryAll<{ lifecycle: string | null; n: number }>(
      `SELECT km.lifecycle AS lifecycle, COUNT(*) AS n
       FROM keyword_metrics km JOIN keywords k ON k.id = km.keyword_id
       WHERE k.is_active = 1
       GROUP BY km.lifecycle`
    );
    const lifecycle: Record<string, number> = {
      emerging: 0, accelerating: 0, peaking: 0, stable: 0, declining: 0,
    };
    for (const r of lifecycleRows) {
      if (r.lifecycle && r.lifecycle in lifecycle) lifecycle[r.lifecycle] = r.n;
    }
    const activeTotal = Object.values(lifecycle).reduce((a, b) => a + b, 0);

    // ─── Emerging niche count (rising keywords, this week) ───
    const emergingCount =
      (await queryOne<{ n: number }>(
        `SELECT COUNT(*) AS n FROM keyword_metrics km JOIN keywords k ON k.id = km.keyword_id
         WHERE k.is_active = 1 AND km.lifecycle IN ('emerging','accelerating')
           AND km.current_interest >= 15`
      ))?.n ?? 0;

    // ─── Vetted breakouts: statistically real, not seasonal ───
    const vettedBreakouts =
      (await queryOne<{ n: number }>(
        `SELECT COUNT(*) AS n FROM keyword_metrics km
         WHERE km.z_score >= 2 AND km.current_interest >= 10
           AND km.velocity_4w > 30 AND km.is_seasonal = 0`
      ))?.n ?? 0;

    // ─── Hottest category by median 4-week velocity (min 5 keywords) ───
    const catVel = await queryAll<{ category: string; velocities: string }>(
      `SELECT k.category AS category, GROUP_CONCAT(km.velocity_4w) AS velocities
       FROM keyword_metrics km JOIN keywords k ON k.id = km.keyword_id
       WHERE k.is_active = 1 AND km.velocity_4w IS NOT NULL
       GROUP BY k.category HAVING COUNT(*) >= 5`
    );
    let hottest: { category: string; median: number } | null = null;
    for (const row of catVel) {
      if (DEEMPHASISED.has(row.category)) continue;
      const vs = row.velocities.split(",").map(Number).sort((a, b) => a - b);
      const mid = Math.floor(vs.length / 2);
      const median = vs.length % 2 ? vs[mid] : (vs[mid - 1] + vs[mid]) / 2;
      if (!hottest || median > hottest.median) hottest = { category: row.category, median };
    }

    // ─── Data trust: share of score components that are real vs fallback ───
    const provRows = await queryAll<{ provenance: string | null }>(
      `SELECT provenance FROM niche_scores WHERE date = (SELECT MAX(date) FROM niche_scores)`
    );
    let real = 0, totalComp = 0;
    for (const r of provRows) {
      if (!r.provenance) continue;
      try {
        for (const v of Object.values(JSON.parse(r.provenance) as Record<string, string>)) {
          totalComp++;
          if (v === "real") real++;
        }
      } catch {
        /* ignore */
      }
    }
    const dataTrustPct = totalComp ? Math.round((real / totalComp) * 100) : null;

    // ─── Opportunity of the week: best vetted, buildable keyword cluster ───
    // Rank by current interest (real search volume) among keywords that are
    // also rising, statistically real, and non-seasonal — so we surface
    // high-volume momentum, not low-base blips like "+1900% on interest 12".
    const lead = await queryOne<{
      keyword: string; category: string; current_interest: number;
      velocity_4w: number; velocity_yoy: number | null; lifecycle: string;
    }>(
      `SELECT k.keyword, k.category, km.current_interest, km.velocity_4w,
              km.velocity_yoy, km.lifecycle
       FROM keyword_metrics km JOIN keywords k ON k.id = km.keyword_id
       WHERE k.is_active = 1 AND km.z_score >= 2 AND km.current_interest >= 40
         AND km.velocity_4w >= 40 AND km.is_seasonal = 0
         AND km.lifecycle IN ('emerging','accelerating')
         AND k.category NOT IN ('beauty','general')
       ORDER BY km.current_interest DESC, km.velocity_4w DESC LIMIT 1`
    );

    let opportunity = null;
    if (lead) {
      const siblings = await queryAll<{ keyword: string; current_interest: number; velocity_4w: number }>(
        `SELECT k.keyword, km.current_interest, km.velocity_4w
         FROM keyword_metrics km JOIN keywords k ON k.id = km.keyword_id
         WHERE k.is_active = 1 AND k.category = ? AND k.keyword != ?
           AND km.lifecycle IN ('emerging','accelerating') AND km.current_interest >= 15
         ORDER BY km.velocity_4w DESC LIMIT 4`,
        [lead.category, lead.keyword]
      );
      const score = await queryOne<{ overall_score: number; margin_score: number }>(
        `SELECT overall_score, margin_score FROM niche_scores
         WHERE category = ? ORDER BY date DESC LIMIT 1`,
        [lead.category]
      );
      const spark = await queryAll<{ s: number }>(
        `SELECT interest_score AS s FROM trend_data td JOIN keywords k ON k.id = td.keyword_id
         WHERE k.keyword = ? ORDER BY td.date DESC LIMIT 12`,
        [lead.keyword]
      );
      opportunity = {
        ...lead,
        siblings,
        overall_score: score?.overall_score ?? null,
        margin_score: score?.margin_score ?? null,
        sparkline: spark.map((r) => r.s).reverse(),
      };
    }

    return NextResponse.json({
      emergingCount,
      vettedBreakouts,
      hottest,
      dataTrustPct,
      lifecycle,
      activeTotal,
      opportunity,
    });
  } catch (error) {
    console.error("Insights API error:", error);
    return NextResponse.json({ error: "Failed to compute insights" }, { status: 500 });
  }
}
