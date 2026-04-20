"use client";

import { useEffect, useState } from "react";

// ──────────────────────────────────────────────────────────
// Types matching the API response
// ──────────────────────────────────────────────────────────

interface CrossValidatedKeyword {
  keyword: string;
  parents: string[];
  parentCount: number;
  sources: string[];
  sourceCount: number;
  suggestedCategory: string;
  avgRelevance: number;
  daysSinceFirstSeen: number;
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

interface NicheHunterData {
  crossValidated: CrossValidatedKeyword[];
  clusters: Cluster[];
  meta: {
    totalPending: number;
    sourcesRepresented: string[];
    clusterCount: number;
  };
}

interface NicheHunterProps {
  colorMap?: Record<string, string>;
}

// ──────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 65) return "#34D399";
  if (score >= 45) return "#FBBF24";
  if (score >= 25) return "#FB923C";
  return "#94A3B8";
}

const SOURCE_LABELS: Record<string, string> = {
  google_related: "Google Related",
  google_category: "Google Category",
  amazon_movers: "Amazon Movers",
  reddit: "Reddit",
  etsy: "Etsy",
  tiktok: "TikTok",
};

function relativeDays(days: number): string {
  if (days < 1) return "today";
  if (days < 2) return "yesterday";
  if (days < 14) return `${Math.floor(days)}d ago`;
  return `${Math.floor(days / 7)}w ago`;
}

// ──────────────────────────────────────────────────────────
// Cluster card
// ──────────────────────────────────────────────────────────

function ClusterCard({
  cluster,
  rank,
  colorMap,
}: {
  cluster: Cluster;
  rank: number;
  colorMap: Record<string, string>;
}) {
  const [expanded, setExpanded] = useState(false);
  const sColor = scoreColor(cluster.score.total);
  const catColor = colorMap[cluster.suggestedCategory] || "#94a3b8";

  return (
    <div className={`glass-card transition-all ${expanded ? "p-5" : "p-4"}`}>
      {/* Collapsed header */}
      <div
        className="flex items-center gap-3 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        {/* Rank */}
        <span
          className="font-mono text-xs font-bold w-6 h-6 rounded-full flex items-center justify-center shrink-0"
          style={{
            backgroundColor: rank <= 3 ? `${sColor}20` : "rgba(255,255,255,0.03)",
            color: rank <= 3 ? sColor : "#64748b",
          }}
        >
          {rank}
        </span>

        {/* Parent + meta */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-slate-200 font-semibold truncate capitalize">
              {cluster.parentKeyword}
            </span>
            <span
              className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/[0.04] capitalize shrink-0"
              style={{ color: catColor }}
            >
              {cluster.suggestedCategory.replace(/_/g, " ")}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className="text-[10px] text-slate-500">
              {cluster.size} keywords
            </span>
            <span className="text-[10px] text-slate-600">·</span>
            <span className="text-[10px] text-slate-500">
              {(cluster.buyerIntent * 100).toFixed(0)}% buyer intent
            </span>
            <span className="text-[10px] text-slate-600">·</span>
            <span className="text-[10px] text-slate-500">
              {relativeDays(cluster.daysSinceNewest)}
            </span>
            {cluster.riskFlags.length > 0 && (
              <span className="text-[10px] text-amber-500/70">
                · {cluster.riskFlags[0]}
              </span>
            )}
          </div>
        </div>

        {/* Score */}
        <div className="flex flex-col items-end gap-0.5 shrink-0 w-16">
          <span
            className="font-mono text-lg font-bold leading-none"
            style={{ color: sColor }}
          >
            {cluster.score.total.toFixed(0)}
          </span>
          <div className="w-full h-[2px] rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${cluster.score.total}%`,
                backgroundColor: sColor,
              }}
            />
          </div>
        </div>

        <span className="text-slate-600 text-xs shrink-0">
          {expanded ? "▾" : "▸"}
        </span>
      </div>

      {/* Expanded */}
      {expanded && (
        <div className="mt-5 pt-5 border-t border-white/[0.04] space-y-4 animate-fade-in">
          {/* Risk flags */}
          {cluster.riskFlags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {cluster.riskFlags.map((flag, i) => (
                <span
                  key={i}
                  className="text-[10px] font-medium px-2 py-1 rounded-lg bg-amber-500/8 text-amber-500/90"
                >
                  ⚠ {flag}
                </span>
              ))}
            </div>
          )}

          {/* Niche scorecard */}
          <div className="space-y-1.5">
            <div className="text-[9px] text-slate-600 uppercase tracking-wider">
              Niche scorecard
            </div>
            {cluster.score.factors.map((f) => (
              <div key={f.key} className="flex items-center gap-3">
                <span className="text-[10px] text-slate-500 w-24 shrink-0">
                  {f.label}
                </span>
                <div className="flex-1 h-[2px] rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${f.value}%`,
                      backgroundColor: scoreColor(f.value),
                    }}
                  />
                </div>
                <span
                  className="text-[10px] font-mono w-9 text-right"
                  style={{ color: scoreColor(f.value) }}
                >
                  {f.value.toFixed(0)}
                </span>
                <span className="text-[9px] text-slate-600 w-10 text-right">
                  ×{f.weight.toFixed(2)}
                </span>
              </div>
            ))}
          </div>

          {/* Source breakdown */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[9px] text-slate-600 uppercase tracking-wider">
              Sources:
            </span>
            {cluster.sources.map((s) => (
              <span
                key={s}
                className="text-[10px] text-slate-400 px-2 py-0.5 rounded-full bg-white/[0.03] border border-white/[0.04]"
              >
                {SOURCE_LABELS[s] || s}
              </span>
            ))}
          </div>

          {/* All keywords */}
          <div className="space-y-2">
            <div className="text-[9px] text-slate-600 uppercase tracking-wider">
              All {cluster.size} keywords in cluster
            </div>
            <div className="flex flex-wrap gap-1.5">
              {cluster.allKeywords.map((kw) => (
                <span
                  key={kw.keyword}
                  className="text-[10px] text-slate-300 px-2 py-1 rounded-lg bg-white/[0.03] border border-white/[0.03]"
                  title={`Relevance: ${kw.relevance.toFixed(2)}`}
                >
                  {kw.keyword}
                </span>
              ))}
            </div>
          </div>

          {/* Action recipe */}
          <div className="space-y-2">
            <div className="text-[9px] text-slate-600 uppercase tracking-wider">
              Action recipe
            </div>
            <ol className="space-y-1.5">
              {cluster.actionRecipe.map((step, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-slate-400">
                  <span className="text-slate-600 font-mono shrink-0 mt-0.5">
                    {i + 1}.
                  </span>
                  <span className="leading-snug">{step}</span>
                </li>
              ))}
            </ol>
          </div>

          {/* Quick links */}
          <div className="flex items-center gap-2 pt-2">
            <button
              onClick={(e) => {
                e.stopPropagation();
                window.open(
                  `https://www.google.com/search?q=${encodeURIComponent(cluster.parentKeyword)}`,
                  "_blank"
                );
              }}
              className="px-3 py-1.5 rounded-lg text-[10px] font-medium text-slate-400 bg-white/[0.04] hover:bg-white/[0.06] transition-colors"
            >
              Google ↗
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                window.open(
                  `https://www.alibaba.com/trade/search?SearchText=${encodeURIComponent(cluster.parentKeyword)}`,
                  "_blank"
                );
              }}
              className="px-3 py-1.5 rounded-lg text-[10px] font-medium text-slate-400 bg-white/[0.04] hover:bg-white/[0.06] transition-colors"
            >
              Alibaba ↗
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                window.open(
                  `https://www.amazon.com/s?k=${encodeURIComponent(cluster.parentKeyword)}`,
                  "_blank"
                );
              }}
              className="px-3 py-1.5 rounded-lg text-[10px] font-medium text-slate-400 bg-white/[0.04] hover:bg-white/[0.06] transition-colors"
            >
              Amazon ↗
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────
// Cross-validated keyword row
// ──────────────────────────────────────────────────────────

function CrossValidatedRow({
  item,
  colorMap,
}: {
  item: CrossValidatedKeyword;
  colorMap: Record<string, string>;
}) {
  const catColor = colorMap[item.suggestedCategory] || "#94a3b8";
  const isMultiSource = item.type === "multi_source";

  return (
    <div className="flex items-center gap-3 py-2.5 px-3 rounded-lg hover:bg-white/[0.02] transition-colors">
      {/* Strength indicator */}
      <span
        className={`shrink-0 w-1 h-8 rounded-full ${
          isMultiSource ? "bg-emerald-400" : "bg-amber-500/70"
        }`}
      />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-slate-200 font-medium">{item.keyword}</span>
          <span
            className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/[0.04] capitalize"
            style={{ color: catColor }}
          >
            {item.suggestedCategory.replace(/_/g, " ")}
          </span>
        </div>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          {isMultiSource ? (
            <span className="text-[10px] text-emerald-400">
              {item.sourceCount} sources: {item.sources.map((s) => SOURCE_LABELS[s] || s).join(", ")}
            </span>
          ) : (
            <span className="text-[10px] text-amber-500/80">
              {item.parentCount} independent paths via{" "}
              {item.parents.slice(0, 2).join(", ")}
              {item.parentCount > 2 && ` +${item.parentCount - 2}`}
            </span>
          )}
          <span className="text-[10px] text-slate-600">·</span>
          <span className="text-[10px] text-slate-500">
            relevance {item.avgRelevance.toFixed(2)}
          </span>
          <span className="text-[10px] text-slate-600">·</span>
          <span className="text-[10px] text-slate-500">
            {relativeDays(item.daysSinceFirstSeen)}
          </span>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────
// Main component
// ──────────────────────────────────────────────────────────

export default function NicheHunter({ colorMap = {} }: NicheHunterProps) {
  const [data, setData] = useState<NicheHunterData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [section, setSection] = useState<"clusters" | "crossval">("clusters");

  useEffect(() => {
    fetch("/api/niche-hunter")
      .then((r) => r.json())
      .then((d) => {
        if (d.error) setError(d.error);
        else setData(d);
      })
      .catch(() => setError("Failed to load niche hunter data"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm animate-pulse">
        Mining niches...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        {error || "No data"}
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Section toggle + meta */}
      <div className="flex items-center justify-between mb-3 shrink-0 flex-wrap gap-2">
        <div className="flex gap-1">
          <button
            onClick={() => setSection("clusters")}
            className={`px-3 py-1.5 rounded-lg text-[10px] font-medium transition-all ${
              section === "clusters"
                ? "bg-white/[0.08] text-slate-200"
                : "text-slate-500 hover:text-slate-400 bg-white/[0.02]"
            }`}
          >
            Emerging Clusters
            <span className="ml-1.5 opacity-50">{data.clusters.length}</span>
          </button>
          <button
            onClick={() => setSection("crossval")}
            className={`px-3 py-1.5 rounded-lg text-[10px] font-medium transition-all ${
              section === "crossval"
                ? "bg-white/[0.08] text-slate-200"
                : "text-slate-500 hover:text-slate-400 bg-white/[0.02]"
            }`}
          >
            Cross-Validated
            <span className="ml-1.5 opacity-50">{data.crossValidated.length}</span>
          </button>
        </div>
        <div className="text-[10px] text-slate-600">
          Mining {data.meta.totalPending} pending · {data.meta.sourcesRepresented.length} source
          {data.meta.sourcesRepresented.length !== 1 ? "s" : ""}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto pr-1 space-y-2">
        {section === "clusters" ? (
          data.clusters.length === 0 ? (
            <div className="text-center text-slate-500 text-sm py-8">
              No clusters with 3+ keywords found yet. Run discovery to populate.
            </div>
          ) : (
            data.clusters.map((c, i) => (
              <ClusterCard
                key={c.id}
                cluster={c}
                rank={i + 1}
                colorMap={colorMap}
              />
            ))
          )
        ) : (
          <>
            {/* Empty-state explainer */}
            {data.crossValidated.length === 0 && (
              <div className="glass-card p-5 text-center space-y-2">
                <div className="text-slate-400 text-sm font-medium">
                  No cross-validated keywords yet
                </div>
                <div className="text-[11px] text-slate-500 leading-relaxed max-w-md mx-auto">
                  Cross-validation finds keywords appearing from multiple discovery
                  sources (Google + Reddit + Etsy + TikTok). You currently have only{" "}
                  <span className="text-slate-300">
                    {data.meta.sourcesRepresented.length} source
                    {data.meta.sourcesRepresented.length !== 1 ? "s" : ""}
                  </span>{" "}
                  represented in pending keywords.
                </div>
                <div className="text-[10px] text-slate-600 pt-2">
                  Reddit + Etsy + TikTok collectors will populate this view as they
                  find keywords matching what Google has already discovered.
                </div>
              </div>
            )}

            {data.crossValidated.length > 0 && (
              <>
                <div className="flex items-center gap-2 px-1">
                  <span className="text-[9px] text-slate-600 uppercase tracking-wider">
                    Legend:
                  </span>
                  <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                    <span className="w-1 h-3 rounded-full bg-emerald-400" />
                    Multi-source
                  </span>
                  <span className="flex items-center gap-1 text-[10px] text-amber-500/80">
                    <span className="w-1 h-3 rounded-full bg-amber-500/70" />
                    Multi-parent (independent paths)
                  </span>
                </div>
                <div className="space-y-0.5">
                  {data.crossValidated.map((item, i) => (
                    <CrossValidatedRow
                      key={`${item.keyword}-${i}`}
                      item={item}
                      colorMap={colorMap}
                    />
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
