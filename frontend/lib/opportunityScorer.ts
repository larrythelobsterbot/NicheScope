import type { KeywordTrend } from "./types";

/**
 * Article Opportunity Scorer
 *
 * Identifies keywords worth writing about RIGHT NOW by combining:
 *  - Momentum (velocity_4w)
 *  - Rankability (sweet spot interest — not too niche, not too saturated)
 *  - Cluster heat (is the whole subcategory trending?)
 *  - Long-tail potential (related rising queries = more H2 sections)
 *  - Acceleration (is 4w growth outpacing 12w? i.e. still building, not peaked)
 */

export interface OpportunityFactor {
  key: string;
  label: string;
  value: number;
  weight: number;
  contribution: number; // value * weight
}

export interface OpportunityReason {
  label: string;
  tone: "strong" | "positive" | "neutral";
}

export type ArticleType =
  | "review"
  | "comparison"
  | "tutorial"
  | "listicle"
  | "buyer_guide"
  | "explainer"
  | "transformation"
  | "first_impressions";

export interface ArticleAngle {
  type: ArticleType;
  title: string;
  reasoning: string;
}

export interface OpportunityScore {
  keyword: string;
  category: string;
  subcategory: string | null;
  score: number; // 0-100
  factors: OpportunityFactor[];
  reasons: OpportunityReason[];
  angles: ArticleAngle[];
  relatedTargets: string[]; // other keywords to include in same article
  current_interest: number;
  velocity_4w: number;
  velocity_12w: number;
  history: number[];
}

// ────────────────────────────────────────────────────────────
// Factor calculators
// ────────────────────────────────────────────────────────────

/** Velocity normalized to 0-100. +100% velocity → 100 score. Negatives → 0. */
function velocityFactor(v4w: number): number {
  return Math.max(0, Math.min((v4w / 100) * 100, 100));
}

/**
 * Bell curve peaking at interest ~55.
 * Below 20: too niche, nobody searches.
 * Above 85: already dominated by authority sites.
 * 40-70 is the rankable sweet spot.
 */
function sweetSpotFactor(interest: number): number {
  const peak = 55;
  const spread = 25;
  const distance = (interest - peak) / spread;
  return Math.exp(-distance * distance) * 100;
}

/**
 * How hot is the surrounding subcategory cluster?
 * If this keyword's subcategory has an avg velocity > 30%, bonus points.
 * Writing about "pdrn serum" when 5 other serums are also rising = strong signal.
 */
function clusterHeatFactor(
  trend: KeywordTrend,
  allTrends: KeywordTrend[]
): { value: number; siblingCount: number } {
  if (!trend.subcategory) return { value: 0, siblingCount: 0 };

  const siblings = allTrends.filter(
    (t) =>
      t.category === trend.category &&
      t.subcategory === trend.subcategory &&
      t.keyword !== trend.keyword
  );

  if (siblings.length === 0) return { value: 0, siblingCount: 0 };

  const avgSiblingVelocity =
    siblings.reduce((sum, s) => sum + s.velocity_4w, 0) / siblings.length;

  // Scale: 0% avg → 0, 50% avg → 100
  const value = Math.max(0, Math.min((avgSiblingVelocity / 50) * 100, 100));
  return { value, siblingCount: siblings.length };
}

/** Related rising queries = long-tail H2 section potential. */
function relatedBreadthFactor(relatedRising: string[]): number {
  const count = relatedRising?.length || 0;
  // 10+ related = full score
  return Math.min((count / 10) * 100, 100);
}

/**
 * Is the keyword still accelerating or already peaked?
 * If v4w > v12w, momentum is building.
 * If v4w < v12w, momentum is fading (already peaked).
 */
function accelerationFactor(v4w: number, v12w: number): number {
  if (v4w <= 0) return 0;
  if (v12w <= 0) return v4w > 20 ? 100 : 50; // emerging from nothing
  const ratio = v4w / v12w;
  // ratio > 1.5 → still accelerating (100), ratio < 0.5 → decelerating (0)
  return Math.max(0, Math.min((ratio - 0.5) * 100, 100));
}

// ────────────────────────────────────────────────────────────
// Reason generation
// ────────────────────────────────────────────────────────────

function buildReasons(
  trend: KeywordTrend,
  factors: OpportunityFactor[],
  clusterSiblings: number
): OpportunityReason[] {
  const reasons: OpportunityReason[] = [];
  const byKey = (k: string) => factors.find((f) => f.key === k)?.value ?? 0;

  // Momentum
  if (trend.velocity_4w >= 100) {
    reasons.push({
      label: `Surging +${trend.velocity_4w.toFixed(0)}% in 4w`,
      tone: "strong",
    });
  } else if (trend.velocity_4w >= 30) {
    reasons.push({
      label: `Rising +${trend.velocity_4w.toFixed(0)}% in 4w`,
      tone: "positive",
    });
  }

  // Sweet spot
  if (byKey("sweetSpot") >= 70) {
    reasons.push({
      label: `Sweet spot interest (${trend.current_interest}) — rankable`,
      tone: "positive",
    });
  } else if (trend.current_interest > 85) {
    reasons.push({
      label: `High interest (${trend.current_interest}) — competitive`,
      tone: "neutral",
    });
  }

  // Cluster heat
  if (byKey("cluster") >= 60 && clusterSiblings >= 2) {
    reasons.push({
      label: `Hot cluster — ${clusterSiblings} siblings also rising`,
      tone: "strong",
    });
  }

  // Long-tail potential
  const relatedCount = trend.related_rising?.length || 0;
  if (relatedCount >= 5) {
    reasons.push({
      label: `${relatedCount} related queries for H2 sections`,
      tone: "positive",
    });
  }

  // Acceleration
  if (
    trend.velocity_4w > 0 &&
    trend.velocity_12w > 0 &&
    trend.velocity_4w > trend.velocity_12w * 1.3
  ) {
    reasons.push({
      label: "Accelerating — 4w beats 12w",
      tone: "strong",
    });
  }

  return reasons;
}

// ────────────────────────────────────────────────────────────
// Article angle suggestions
// ────────────────────────────────────────────────────────────

/**
 * Generates article angle suggestions based on keyword pattern matching.
 * Uses linguistic cues to determine the most natural article format.
 */
export function suggestAngles(
  keyword: string,
  relatedRising: string[] = []
): ArticleAngle[] {
  const kw = keyword.toLowerCase();
  const angles: ArticleAngle[] = [];
  const titleCase = (s: string) =>
    s.replace(/\b\w/g, (c) => c.toUpperCase());

  // Pattern: "X vs Y"
  if (/\bvs\b|\bversus\b/.test(kw)) {
    angles.push({
      type: "comparison",
      title: `${titleCase(keyword)}: Which Is Actually Better?`,
      reasoning: "Comparison queries = ready-to-decide buyers. High conversion intent.",
    });
    return angles;
  }

  // Pattern: "how to X" / "how do X"
  if (/\bhow (to|do|does|can)\b/.test(kw)) {
    angles.push({
      type: "tutorial",
      title: titleCase(keyword) + ": A Step-by-Step Guide",
      reasoning: "Instructional intent. Screenshots/video perform well.",
    });
    return angles;
  }

  // Pattern: "best X" / "top X"
  if (/\b(best|top|greatest)\b/.test(kw)) {
    angles.push({
      type: "listicle",
      title: titleCase(keyword) + " (2026 Tested & Ranked)",
      reasoning:
        "Roundup queries love listicles with clear rankings and affiliate potential.",
    });
    return angles;
  }

  // Pattern: "X review" / "X reviews"
  if (/\breview(s)?\b/.test(kw)) {
    angles.push({
      type: "review",
      title: titleCase(keyword.replace(/reviews?/, "").trim()) +
        " — Honest Review After 30 Days",
      reasoning: "Review intent = purchase consideration. Include pros/cons and affiliate link.",
    });
    return angles;
  }

  // Pattern: "before and after" / "before after"
  if (/before.{0,5}after/.test(kw)) {
    angles.push({
      type: "transformation",
      title: titleCase(keyword) + ": Real Results & Photos",
      reasoning: "Visual transformation posts get massive social shares.",
    });
    return angles;
  }

  // Pattern: "what is X"
  if (/\bwhat is\b|\bwhat are\b/.test(kw)) {
    angles.push({
      type: "explainer",
      title: titleCase(keyword) + "? The Complete Beginner's Guide",
      reasoning: "Definition intent. Rank for the core term + pull in long-tail.",
    });
    return angles;
  }

  // Pattern: brand + product (e.g. "medicube pdrn", "numbuzin no 9")
  const words = kw.split(/\s+/);
  const looksLikeBrandProduct =
    words.length >= 2 &&
    /^[a-z0-9]+$/.test(words[0]) &&
    !["best", "top", "how", "what", "why", "korean", "pdrn"].includes(words[0]);

  if (looksLikeBrandProduct) {
    angles.push({
      type: "first_impressions",
      title: titleCase(keyword) + ": First Impressions & Is It Worth It?",
      reasoning:
        "Specific product searches = buyer intent. Write a deep review with affiliate link before competitors do.",
    });
    angles.push({
      type: "comparison",
      title: `${titleCase(keyword)} vs The Alternatives`,
      reasoning:
        "Secondary angle — capture people comparing this product to rivals.",
    });
    return angles;
  }

  // Generic category keyword (e.g. "pdrn serum", "korean sunscreen")
  angles.push({
    type: "buyer_guide",
    title: `The ${titleCase(keyword)} Buyer's Guide (2026)`,
    reasoning:
      "Broad category term. Build a hub page covering what it is, how to choose, and top picks.",
  });
  angles.push({
    type: "listicle",
    title: `Best ${titleCase(keyword)}: Tested & Ranked`,
    reasoning:
      "Parallel angle for commercial intent searchers already ready to buy.",
  });

  // If we have rich related queries, also suggest an explainer
  if (relatedRising.length >= 3) {
    angles.push({
      type: "explainer",
      title: `What Is ${titleCase(keyword)}? Everything You Need to Know`,
      reasoning: `${relatedRising.length} related queries give you ready-made H2 sections.`,
    });
  }

  return angles.slice(0, 3);
}

// ────────────────────────────────────────────────────────────
// Main scoring function
// ────────────────────────────────────────────────────────────

const WEIGHTS = {
  velocity: 0.35,
  sweetSpot: 0.25,
  cluster: 0.2,
  related: 0.1,
  acceleration: 0.1,
} as const;

export function scoreOpportunity(
  trend: KeywordTrend,
  allTrends: KeywordTrend[]
): OpportunityScore {
  const velocity = velocityFactor(trend.velocity_4w);
  const sweetSpot = sweetSpotFactor(trend.current_interest);
  const cluster = clusterHeatFactor(trend, allTrends);
  const related = relatedBreadthFactor(trend.related_rising || []);
  const acceleration = accelerationFactor(
    trend.velocity_4w,
    trend.velocity_12w
  );

  const factors: OpportunityFactor[] = [
    {
      key: "velocity",
      label: "Momentum",
      value: velocity,
      weight: WEIGHTS.velocity,
      contribution: velocity * WEIGHTS.velocity,
    },
    {
      key: "sweetSpot",
      label: "Rankability",
      value: sweetSpot,
      weight: WEIGHTS.sweetSpot,
      contribution: sweetSpot * WEIGHTS.sweetSpot,
    },
    {
      key: "cluster",
      label: "Cluster Heat",
      value: cluster.value,
      weight: WEIGHTS.cluster,
      contribution: cluster.value * WEIGHTS.cluster,
    },
    {
      key: "related",
      label: "Long-tail",
      value: related,
      weight: WEIGHTS.related,
      contribution: related * WEIGHTS.related,
    },
    {
      key: "acceleration",
      label: "Accelerating",
      value: acceleration,
      weight: WEIGHTS.acceleration,
      contribution: acceleration * WEIGHTS.acceleration,
    },
  ];

  const score = factors.reduce((sum, f) => sum + f.contribution, 0);

  const reasons = buildReasons(trend, factors, cluster.siblingCount);
  const angles = suggestAngles(trend.keyword, trend.related_rising || []);

  // Related targets = hot siblings in same subcategory + related rising queries
  const relatedTargets: string[] = [];
  if (trend.subcategory) {
    const siblings = allTrends
      .filter(
        (t) =>
          t.category === trend.category &&
          t.subcategory === trend.subcategory &&
          t.keyword !== trend.keyword &&
          t.velocity_4w > 0
      )
      .sort((a, b) => b.velocity_4w - a.velocity_4w)
      .slice(0, 4)
      .map((t) => t.keyword);
    relatedTargets.push(...siblings);
  }
  if (trend.related_rising && trend.related_rising.length > 0) {
    relatedTargets.push(
      ...trend.related_rising
        .filter((r) => !relatedTargets.includes(r))
        .slice(0, 4)
    );
  }

  const history = trend.history
    .slice()
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((h) => h.interest_score);

  return {
    keyword: trend.keyword,
    category: trend.category,
    subcategory: trend.subcategory,
    score,
    factors,
    reasons,
    angles,
    relatedTargets,
    current_interest: trend.current_interest,
    velocity_4w: trend.velocity_4w,
    velocity_12w: trend.velocity_12w,
    history,
  };
}

/** Rank all trends and return top N opportunities. */
export function rankOpportunities(
  trends: KeywordTrend[],
  limit: number = 20
): OpportunityScore[] {
  return trends
    .filter((t) => t.history.length >= 2) // need minimum data
    .map((t) => scoreOpportunity(t, trends))
    .filter((o) => o.score > 15) // cut the dead wood
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
}
