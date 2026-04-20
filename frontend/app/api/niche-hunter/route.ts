import { NextResponse } from "next/server";
import { queryAll } from "@/lib/db";

// ──────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────

interface PendingRow {
  id: number;
  keyword: string;
  suggested_category: string;
  source: string;
  parent_keyword: string;
  relevance_score: number;
  discovered_at: string;
}

interface NicheScoreRow {
  category: string;
  trend_score: number;
  margin_score: number;
  competition_score: number;
  sourcing_score: number;
  content_score: number;
  repeat_purchase_score: number;
  overall_score: number;
}

interface CrossValidatedKeyword {
  keyword: string;
  parents: string[];
  parentCount: number;
  sources: string[];
  sourceCount: number;
  suggestedCategory: string;
  avgRelevance: number;
  daysSinceFirstSeen: number;
  // True cross-source = appeared from 2+ different sources
  // Fallback = appeared as child of 2+ different parents (single-source data)
  type: "multi_source" | "multi_parent";
}

interface ScoreFactor {
  key: string;
  label: string;
  value: number;
  weight: number;
}

interface ClusterScore {
  total: number;
  factors: ScoreFactor[];
}

interface Cluster {
  id: string;
  parentKeyword: string;
  suggestedCategory: string;
  size: number;
  sourceDiversity: number;
  avgRelevance: number;
  daysSinceNewest: number;
  daysSinceOldest: number;
  buyerIntent: number;
  sampleKeywords: { keyword: string; relevance: number }[];
  allKeywords: { keyword: string; relevance: number }[];
  sources: string[];
  score: ClusterScore;
  riskFlags: string[];
  categoryNicheScore: NicheScoreRow | null;
  actionRecipe: string[];
}

// ──────────────────────────────────────────────────────────
// Buyer intent detection
// ──────────────────────────────────────────────────────────

const BUYER_INTENT_PATTERNS = [
  /\bbest\b/i,
  /\btop\b/i,
  /\breview/i,
  /\bvs\b|\bversus\b/i,
  /\bprice/i,
  /\bcheap/i,
  /\bdeal/i,
  /\bbuy\b/i,
  /\bwhere to\b/i,
  /\bnear me\b/i,
  /\bworth it\b/i,
  /\balternative/i,
  /\brecommend/i,
  /\bcompare/i,
  /\bbrand/i,
  /\bdiscount/i,
  /\bcoupon/i,
];

function buyerIntentScore(keywords: string[]): number {
  if (keywords.length === 0) return 0;
  const matches = keywords.filter((k) =>
    BUYER_INTENT_PATTERNS.some((p) => p.test(k))
  );
  return matches.length / keywords.length;
}

// ──────────────────────────────────────────────────────────
// Cluster scoring
// ──────────────────────────────────────────────────────────

const WEIGHTS = {
  size: 0.2,
  buyerIntent: 0.25,
  recency: 0.15,
  sourceDiversity: 0.1,
  relevance: 0.1,
  margin: 0.1,
  repeatPurchase: 0.1,
} as const;

function scoreCluster(
  cluster: Omit<Cluster, "score" | "riskFlags" | "actionRecipe">
): ClusterScore {
  // Size: 3-15 keywords normalized
  const sizeNorm = Math.min((cluster.size - 2) / 12, 1) * 100;

  // Buyer intent: already 0-1
  const buyerNorm = cluster.buyerIntent * 100;

  // Recency: newer = better (max bonus if discovered in last 7 days)
  const recencyNorm = Math.max(0, 100 - cluster.daysSinceNewest * 4);

  // Source diversity: max ~6 sources
  const sourceNorm = Math.min(cluster.sourceDiversity / 4, 1) * 100;

  // Average relevance: 0-1 → 0-100
  const relevanceNorm = cluster.avgRelevance * 100;

  // Margin & repeat from niche scores (0-100)
  const marginNorm = cluster.categoryNicheScore?.margin_score ?? 50;
  const repeatNorm = cluster.categoryNicheScore?.repeat_purchase_score ?? 50;

  const factors: ScoreFactor[] = [
    {
      key: "buyerIntent",
      label: "Buyer Intent",
      value: buyerNorm,
      weight: WEIGHTS.buyerIntent,
    },
    {
      key: "size",
      label: "Cluster Size",
      value: sizeNorm,
      weight: WEIGHTS.size,
    },
    {
      key: "recency",
      label: "Recency",
      value: recencyNorm,
      weight: WEIGHTS.recency,
    },
    {
      key: "sourceDiversity",
      label: "Source Diversity",
      value: sourceNorm,
      weight: WEIGHTS.sourceDiversity,
    },
    {
      key: "relevance",
      label: "Avg Relevance",
      value: relevanceNorm,
      weight: WEIGHTS.relevance,
    },
    {
      key: "margin",
      label: "Margin Tier",
      value: marginNorm,
      weight: WEIGHTS.margin,
    },
    {
      key: "repeatPurchase",
      label: "Repeat Purchase",
      value: repeatNorm,
      weight: WEIGHTS.repeatPurchase,
    },
  ];

  const total = factors.reduce((sum, f) => sum + f.value * f.weight, 0);

  return { total, factors };
}

// ──────────────────────────────────────────────────────────
// Risk flags
// ──────────────────────────────────────────────────────────

function detectRiskFlags(cluster: Omit<Cluster, "score" | "riskFlags" | "actionRecipe">): string[] {
  const flags: string[] = [];

  if (cluster.sourceDiversity === 1) {
    flags.push("Single-source signal");
  }
  if (cluster.size < 5) {
    flags.push("Small cluster");
  }
  if (cluster.daysSinceNewest > 14) {
    flags.push("Stale discovery");
  }
  if (cluster.buyerIntent < 0.1) {
    flags.push("Low purchase intent");
  }
  if (cluster.avgRelevance < 0.4) {
    flags.push("Low relevance scores");
  }

  // Detect "news/trending topic" parents — usually noise
  const newsPatterns = [
    /\bnews\b/i,
    /\btoday\b/i,
    /\bopenai\b/i,
    /\bai\b.*\b(today|news)\b/i,
  ];
  if (newsPatterns.some((p) => p.test(cluster.parentKeyword))) {
    flags.push("Trending news topic (not a niche)");
  }

  return flags;
}

// ──────────────────────────────────────────────────────────
// Action recipes
// ──────────────────────────────────────────────────────────

function generateActionRecipe(cluster: Omit<Cluster, "actionRecipe">): string[] {
  const recipe: string[] = [];
  const cat = cluster.suggestedCategory.replace(/_/g, " ");
  const parent = cluster.parentKeyword;

  // Source step
  recipe.push(
    `Source: Search Alibaba/AliExpress for "${parent} private label" — look for MOQ < 500 units`
  );

  // Validate step
  if (cluster.buyerIntent > 0.2) {
    recipe.push(
      `Validate: Buy 2-3 samples from top suppliers, write hands-on reviews to capture buyer-intent traffic`
    );
  } else {
    recipe.push(
      `Validate: Run a $20 Reddit ad in a relevant ${cat} subreddit to test demand`
    );
  }

  // Content step
  const topKeywords = cluster.sampleKeywords.slice(0, 3).map((k) => k.keyword);
  recipe.push(
    `Content moat: Use Write About tab to publish 3 articles targeting: ${topKeywords.join(", ")}`
  );

  // Margin/repeat warning
  if (cluster.categoryNicheScore) {
    const margin = cluster.categoryNicheScore.margin_score;
    if (margin < 50) {
      recipe.push(
        `⚠ Low margin category (${margin}/100) — focus on bundling or affiliate model, not own-brand`
      );
    } else if (margin >= 70) {
      recipe.push(
        `Strong margin category (${margin}/100) — own-brand or private label viable`
      );
    }
  }

  return recipe;
}

// ──────────────────────────────────────────────────────────
// Build clusters from pending data
// ──────────────────────────────────────────────────────────

function buildClusters(
  rows: PendingRow[],
  nicheScoreMap: Map<string, NicheScoreRow>
): Cluster[] {
  // Group by parent_keyword (the natural cluster grain)
  const parentMap = new Map<string, PendingRow[]>();
  for (const row of rows) {
    if (!row.parent_keyword) continue;
    const list = parentMap.get(row.parent_keyword) || [];
    list.push(row);
    parentMap.set(row.parent_keyword, list);
  }

  const now = Date.now();
  const clusters: Cluster[] = [];

  parentMap.forEach((children, parent) => {
    if (children.length < 3) return; // need minimum cluster size

    // Determine dominant category (most common suggested_category among children)
    const catCounts = new Map<string, number>();
    for (const c of children) {
      catCounts.set(
        c.suggested_category,
        (catCounts.get(c.suggested_category) || 0) + 1
      );
    }
    const dominantCategory =
      Array.from(catCounts.entries()).sort((a, b) => b[1] - a[1])[0]?.[0] ||
      "uncategorized";

    // Source diversity
    const sourceSet = new Set(children.map((c) => c.source));

    // Date stats
    const dates = children.map((c) => new Date(c.discovered_at).getTime());
    const newest = Math.max(...dates);
    const oldest = Math.min(...dates);
    const daysSinceNewest = (now - newest) / (1000 * 60 * 60 * 24);
    const daysSinceOldest = (now - oldest) / (1000 * 60 * 60 * 24);

    // Avg relevance
    const avgRelevance =
      children.reduce((sum, c) => sum + (c.relevance_score || 0), 0) /
      children.length;

    // Buyer intent
    const buyerIntent = buyerIntentScore(children.map((c) => c.keyword));

    // Top keywords by relevance
    const sortedKeywords = children
      .slice()
      .sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0))
      .map((c) => ({ keyword: c.keyword, relevance: c.relevance_score || 0 }));

    const baseCluster = {
      id: Buffer.from(parent).toString("base64").slice(0, 12),
      parentKeyword: parent,
      suggestedCategory: dominantCategory,
      size: children.length,
      sourceDiversity: sourceSet.size,
      avgRelevance,
      daysSinceNewest,
      daysSinceOldest,
      buyerIntent,
      sampleKeywords: sortedKeywords.slice(0, 5),
      allKeywords: sortedKeywords,
      sources: Array.from(sourceSet),
      categoryNicheScore: nicheScoreMap.get(dominantCategory) || null,
    };

    const score = scoreCluster(baseCluster);
    const riskFlags = detectRiskFlags(baseCluster);
    const actionRecipe = generateActionRecipe({ ...baseCluster, score, riskFlags });

    clusters.push({
      ...baseCluster,
      score,
      riskFlags,
      actionRecipe,
    });
  });

  // Sort by total score desc
  return clusters.sort((a, b) => b.score.total - a.score.total);
}

// ──────────────────────────────────────────────────────────
// Build cross-validated keywords
// ──────────────────────────────────────────────────────────

function buildCrossValidated(rows: PendingRow[]): CrossValidatedKeyword[] {
  // Group by keyword
  const kwMap = new Map<string, PendingRow[]>();
  for (const row of rows) {
    const list = kwMap.get(row.keyword) || [];
    list.push(row);
    kwMap.set(row.keyword, list);
  }

  const now = Date.now();
  const results: CrossValidatedKeyword[] = [];

  kwMap.forEach((instances, keyword) => {
    const sources = new Set(instances.map((i) => i.source));
    const parents = new Set(
      instances.map((i) => i.parent_keyword).filter((p) => p && p.length > 0)
    );

    // Multi-source = strongest signal
    if (sources.size >= 2) {
      const oldest = Math.min(
        ...instances.map((i) => new Date(i.discovered_at).getTime())
      );
      results.push({
        keyword,
        parents: Array.from(parents),
        parentCount: parents.size,
        sources: Array.from(sources),
        sourceCount: sources.size,
        suggestedCategory: instances[0].suggested_category,
        avgRelevance:
          instances.reduce((s, i) => s + (i.relevance_score || 0), 0) /
          instances.length,
        daysSinceFirstSeen: (now - oldest) / (1000 * 60 * 60 * 24),
        type: "multi_source",
      });
      return;
    }

    // Multi-parent fallback (single-source data) = independent paths
    if (parents.size >= 2) {
      const oldest = Math.min(
        ...instances.map((i) => new Date(i.discovered_at).getTime())
      );
      results.push({
        keyword,
        parents: Array.from(parents),
        parentCount: parents.size,
        sources: Array.from(sources),
        sourceCount: sources.size,
        suggestedCategory: instances[0].suggested_category,
        avgRelevance:
          instances.reduce((s, i) => s + (i.relevance_score || 0), 0) /
          instances.length,
        daysSinceFirstSeen: (now - oldest) / (1000 * 60 * 60 * 24),
        type: "multi_parent",
      });
    }
  });

  // Sort: multi-source first, then by parent count, then by relevance
  results.sort((a, b) => {
    if (a.type !== b.type) return a.type === "multi_source" ? -1 : 1;
    if (b.parentCount !== a.parentCount) return b.parentCount - a.parentCount;
    return b.avgRelevance - a.avgRelevance;
  });

  return results.slice(0, 30);
}

// ──────────────────────────────────────────────────────────
// Route handler
// ──────────────────────────────────────────────────────────

export async function GET() {
  try {
    const pending = await queryAll<PendingRow>(
      `SELECT id, keyword, suggested_category, source, parent_keyword,
              relevance_score, discovered_at
       FROM pending_keywords
       WHERE status = 'pending'
       ORDER BY discovered_at DESC`
    );

    const nicheScores = await queryAll<NicheScoreRow>(
      `SELECT category, trend_score, margin_score, competition_score,
              sourcing_score, content_score, repeat_purchase_score, overall_score
       FROM niche_scores
       WHERE date = (SELECT MAX(date) FROM niche_scores)`
    );

    const nicheScoreMap = new Map<string, NicheScoreRow>();
    for (const ns of nicheScores) {
      nicheScoreMap.set(ns.category, ns);
    }

    const crossValidated = buildCrossValidated(pending);
    const clusters = buildClusters(pending, nicheScoreMap);

    return NextResponse.json({
      crossValidated,
      clusters: clusters.slice(0, 30),
      meta: {
        totalPending: pending.length,
        sourcesRepresented: Array.from(new Set(pending.map((p) => p.source))),
        clusterCount: clusters.length,
      },
    });
  } catch (error) {
    console.error("Niche hunter API error:", error);
    return NextResponse.json(
      { error: "Failed to compute niche hunter data" },
      { status: 500 }
    );
  }
}
