"use client";

import { useMemo, useState, useEffect } from "react";
import { KeywordTrend } from "@/lib/types";
import {
  rankOpportunities,
  type OpportunityScore,
  type ArticleType,
} from "@/lib/opportunityScorer";
import Sparkline from "./Sparkline";

interface ArticleOpportunitiesProps {
  trends: KeywordTrend[];
  colorMap?: Record<string, string>;
}

// ──────────────────────────────────────────────────────────
// LocalStorage persistence for written/dismissed state
// ──────────────────────────────────────────────────────────
const STORAGE_KEY = "nichescope:article-status";

type ArticleStatus = "written" | "dismissed";

function loadStatus(): Record<string, ArticleStatus> {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveStatus(status: Record<string, ArticleStatus>) {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(status));
}

// ──────────────────────────────────────────────────────────
// Visual helpers
// ──────────────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 70) return "#34D399"; // emerald
  if (score >= 50) return "#FBBF24"; // amber
  if (score >= 30) return "#FB923C"; // orange
  return "#94A3B8"; // slate
}

const ARTICLE_TYPE_LABELS: Record<ArticleType, string> = {
  review: "Review",
  comparison: "Comparison",
  tutorial: "Tutorial",
  listicle: "Listicle",
  buyer_guide: "Buyer Guide",
  explainer: "Explainer",
  transformation: "Transformation",
  first_impressions: "First Impressions",
};

const ARTICLE_TYPE_ICONS: Record<ArticleType, string> = {
  review: "★",
  comparison: "⚖",
  tutorial: "▶",
  listicle: "☰",
  buyer_guide: "❖",
  explainer: "?",
  transformation: "↯",
  first_impressions: "◎",
};

// ──────────────────────────────────────────────────────────
// Opportunity card
// ──────────────────────────────────────────────────────────

interface OpportunityCardProps {
  opportunity: OpportunityScore;
  rank: number;
  colorMap: Record<string, string>;
  status?: ArticleStatus;
  onMarkWritten: () => void;
  onDismiss: () => void;
  onRestore: () => void;
}

function OpportunityCard({
  opportunity,
  rank,
  colorMap,
  status,
  onMarkWritten,
  onDismiss,
  onRestore,
}: OpportunityCardProps) {
  const [expanded, setExpanded] = useState(false);
  const color = colorMap[opportunity.category] || "#94a3b8";
  const sColor = scoreColor(opportunity.score);
  const direction =
    opportunity.velocity_4w > 0
      ? "up"
      : opportunity.velocity_4w < 0
      ? "down"
      : "flat";

  return (
    <div
      className={`glass-card transition-all ${
        status ? "opacity-50" : ""
      } ${expanded ? "p-5" : "p-4"}`}
    >
      {/* Collapsed header row */}
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

        {/* Keyword + meta */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-slate-200 font-medium truncate">
              {opportunity.keyword}
            </span>
            {status === "written" && (
              <span className="text-[9px] font-mono text-emerald-400 bg-emerald-400/10 px-1.5 py-0.5 rounded">
                WRITTEN
              </span>
            )}
            {status === "dismissed" && (
              <span className="text-[9px] font-mono text-slate-500 bg-white/[0.03] px-1.5 py-0.5 rounded">
                DISMISSED
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className="text-[10px] capitalize" style={{ color }}>
              {opportunity.category.replace(/_/g, " ")}
            </span>
            {opportunity.subcategory && (
              <span className="text-[10px] text-slate-500 px-1.5 py-0.5 rounded-full bg-white/[0.03] capitalize">
                {opportunity.subcategory.replace(/_/g, " ")}
              </span>
            )}
            {opportunity.reasons.slice(0, 1).map((r, i) => (
              <span
                key={i}
                className="text-[10px] text-slate-500 hidden md:inline"
              >
                · {r.label}
              </span>
            ))}
          </div>
        </div>

        {/* Sparkline */}
        <div className="hidden md:block shrink-0">
          <Sparkline
            data={opportunity.history}
            width={72}
            height={22}
            trend={direction}
            strokeWidth={1.25}
            showBaseline={false}
          />
        </div>

        {/* Score */}
        <div className="flex flex-col items-end gap-0.5 shrink-0 w-16">
          <span
            className="font-mono text-lg font-bold leading-none"
            style={{ color: sColor }}
          >
            {opportunity.score.toFixed(0)}
          </span>
          <div className="w-full h-[2px] rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${opportunity.score}%`,
                backgroundColor: sColor,
              }}
            />
          </div>
        </div>

        {/* Expand indicator */}
        <span className="text-slate-600 text-xs shrink-0">
          {expanded ? "▾" : "▸"}
        </span>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="mt-5 pt-5 border-t border-white/[0.04] space-y-4 animate-fade-in">
          {/* Reasons */}
          {opportunity.reasons.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {opportunity.reasons.map((r, i) => (
                <span
                  key={i}
                  className="text-[10px] font-medium px-2 py-1 rounded-lg"
                  style={{
                    backgroundColor:
                      r.tone === "strong"
                        ? "rgba(52, 211, 153, 0.1)"
                        : r.tone === "positive"
                        ? "rgba(251, 191, 36, 0.08)"
                        : "rgba(148, 163, 184, 0.06)",
                    color:
                      r.tone === "strong"
                        ? "#34D399"
                        : r.tone === "positive"
                        ? "#FBBF24"
                        : "#94A3B8",
                  }}
                >
                  {r.label}
                </span>
              ))}
            </div>
          )}

          {/* Factor breakdown */}
          <div className="space-y-1.5">
            <div className="text-[9px] text-slate-600 uppercase tracking-wider">
              Score breakdown
            </div>
            {opportunity.factors.map((f) => (
              <div key={f.key} className="flex items-center gap-3">
                <span className="text-[10px] text-slate-500 w-20 shrink-0">
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
                <span className="text-[9px] text-slate-600 w-8 text-right">
                  ×{f.weight.toFixed(2)}
                </span>
              </div>
            ))}
          </div>

          {/* Article angles */}
          <div className="space-y-2">
            <div className="text-[9px] text-slate-600 uppercase tracking-wider">
              Suggested article angles
            </div>
            {opportunity.angles.map((angle, i) => (
              <div
                key={i}
                className="p-3 rounded-lg bg-white/[0.02] border border-white/[0.04]"
              >
                <div className="flex items-start gap-3">
                  <span
                    className="text-lg shrink-0"
                    style={{ color: sColor, lineHeight: "1" }}
                  >
                    {ARTICLE_TYPE_ICONS[angle.type]}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="text-[9px] font-mono uppercase tracking-wider text-slate-500">
                        {ARTICLE_TYPE_LABELS[angle.type]}
                      </span>
                    </div>
                    <div className="text-sm text-slate-200 font-medium leading-snug mb-1">
                      {angle.title}
                    </div>
                    <div className="text-[11px] text-slate-500 leading-snug">
                      {angle.reasoning}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Related targets */}
          {opportunity.relatedTargets.length > 0 && (
            <div className="space-y-2">
              <div className="text-[9px] text-slate-600 uppercase tracking-wider">
                Bundle these keywords in the same article
              </div>
              <div className="flex flex-wrap gap-1.5">
                {opportunity.relatedTargets.map((kw) => (
                  <span
                    key={kw}
                    className="text-[10px] text-slate-400 px-2 py-1 rounded-full bg-white/[0.03] border border-white/[0.03]"
                  >
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-2">
            {status ? (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onRestore();
                }}
                className="px-3 py-1.5 rounded-lg text-[10px] font-medium text-slate-400 bg-white/[0.04] hover:bg-white/[0.06] transition-colors"
              >
                Restore
              </button>
            ) : (
              <>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onMarkWritten();
                  }}
                  className="px-3 py-1.5 rounded-lg text-[10px] font-medium bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition-colors"
                >
                  ✓ Mark as written
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDismiss();
                  }}
                  className="px-3 py-1.5 rounded-lg text-[10px] font-medium text-slate-500 hover:text-slate-300 bg-white/[0.02] hover:bg-white/[0.04] transition-colors"
                >
                  Not for me
                </button>
              </>
            )}
            <button
              onClick={(e) => {
                e.stopPropagation();
                const query = encodeURIComponent(opportunity.keyword);
                window.open(`https://www.google.com/search?q=${query}`, "_blank");
              }}
              className="ml-auto px-3 py-1.5 rounded-lg text-[10px] font-medium text-slate-500 hover:text-slate-300 transition-colors"
            >
              Google it ↗
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────
// Main component
// ──────────────────────────────────────────────────────────

export default function ArticleOpportunities({
  trends,
  colorMap = {},
}: ArticleOpportunitiesProps) {
  const [statusMap, setStatusMap] = useState<Record<string, ArticleStatus>>({});
  const [showHidden, setShowHidden] = useState(false);

  // Load persisted status on mount
  useEffect(() => {
    setStatusMap(loadStatus());
  }, []);

  const opportunities = useMemo(
    () => rankOpportunities(trends, 30),
    [trends]
  );

  // Split into active / hidden
  const active = opportunities.filter((o) => !statusMap[o.keyword]);
  const hidden = opportunities.filter((o) => statusMap[o.keyword]);

  const visible = showHidden ? hidden : active;

  const updateStatus = (keyword: string, status: ArticleStatus | null) => {
    setStatusMap((prev) => {
      const next = { ...prev };
      if (status === null) {
        delete next[keyword];
      } else {
        next[keyword] = status;
      }
      saveStatus(next);
      return next;
    });
  };

  if (opportunities.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-500 text-sm text-center gap-2">
        <div>Not enough trend data to score opportunities yet.</div>
        <div className="text-[10px] text-slate-600">
          Need keywords with at least 2 data points and positive momentum.
        </div>
      </div>
    );
  }

  const writtenCount = Object.values(statusMap).filter((s) => s === "written").length;

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header summary */}
      <div className="flex items-center justify-between mb-3 shrink-0 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <div className="text-[10px] text-slate-500">
            <span className="text-slate-300 font-semibold">{active.length}</span> opportunities ·{" "}
            <span className="text-emerald-400 font-semibold">{writtenCount}</span> written
          </div>
        </div>
        {hidden.length > 0 && (
          <button
            onClick={() => setShowHidden(!showHidden)}
            className="text-[10px] text-slate-500 hover:text-slate-300 transition-colors"
          >
            {showHidden ? "← Back to active" : `Show hidden (${hidden.length})`}
          </button>
        )}
      </div>

      {/* Opportunity list */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {visible.length === 0 ? (
          <div className="text-center text-slate-500 text-sm py-8">
            {showHidden
              ? "Nothing hidden yet."
              : "All active opportunities have been actioned. Check hidden list."}
          </div>
        ) : (
          visible.map((opp, i) => (
            <OpportunityCard
              key={opp.keyword}
              opportunity={opp}
              rank={i + 1}
              colorMap={colorMap}
              status={statusMap[opp.keyword]}
              onMarkWritten={() => updateStatus(opp.keyword, "written")}
              onDismiss={() => updateStatus(opp.keyword, "dismissed")}
              onRestore={() => updateStatus(opp.keyword, null)}
            />
          ))
        )}
      </div>
    </div>
  );
}
