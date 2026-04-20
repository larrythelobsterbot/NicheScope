"use client";

import { useMemo } from "react";
import { KeywordTrend } from "@/lib/types";
import { formatPercent } from "@/lib/utils";
import Sparkline from "./Sparkline";

interface HotNowProps {
  trends: KeywordTrend[];
  colorMap?: Record<string, string>;
  onKeywordClick?: (keyword: string) => void;
}

/** A single hot keyword row with big sparkline and velocity badge. */
function HotRow({
  trend,
  rank,
  color,
  maxVelocity,
  onClick,
}: {
  trend: KeywordTrend;
  rank: number;
  color: string;
  maxVelocity: number;
  onClick?: () => void;
}) {
  const history = trend.history
    .slice()
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((h) => h.interest_score);

  const v4w = trend.velocity_4w;
  const v12w = trend.velocity_12w;
  const direction = v4w > 0 ? "up" : v4w < 0 ? "down" : "flat";

  // Heat intensity: how hot is this relative to the hottest keyword
  const heat = maxVelocity > 0 ? Math.min(v4w / maxVelocity, 1) : 0;

  return (
    <div
      className="flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-white/[0.03] transition-all cursor-pointer group"
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter") onClick?.();
      }}
    >
      {/* Rank */}
      <span
        className="font-mono text-xs font-bold w-6 h-6 rounded-full flex items-center justify-center shrink-0"
        style={{
          backgroundColor:
            rank <= 3
              ? `${color}20`
              : "rgba(255,255,255,0.03)",
          color: rank <= 3 ? color : "#64748b",
        }}
      >
        {rank}
      </span>

      {/* Keyword + meta */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-200 font-medium truncate group-hover:text-white transition-colors">
            {trend.keyword}
          </span>
          {trend.subcategory && (
            <span className="text-[9px] text-slate-500 px-1.5 py-0.5 rounded-full bg-white/[0.03] capitalize shrink-0 hidden sm:inline">
              {trend.subcategory.replace(/_/g, " ")}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 mt-0.5">
          <span
            className="text-[10px] capitalize"
            style={{ color }}
          >
            {trend.category.replace(/_/g, " ")}
          </span>
          <span className="text-[10px] text-slate-600">
            Interest: {trend.current_interest}
          </span>
        </div>
      </div>

      {/* Sparkline — larger than usual */}
      <div className="shrink-0 hidden md:block">
        <Sparkline
          data={history}
          width={96}
          height={28}
          trend={direction}
          strokeWidth={1.5}
          showBaseline={true}
        />
      </div>

      {/* Velocity badges */}
      <div className="flex flex-col items-end gap-0.5 shrink-0">
        <span
          className="font-mono text-xs font-bold px-2.5 py-1 rounded-lg"
          style={{
            backgroundColor:
              v4w > 0
                ? `rgba(52, 211, 153, ${0.08 + heat * 0.15})`
                : v4w < 0
                ? "rgba(251, 113, 133, 0.1)"
                : "rgba(100, 116, 139, 0.08)",
            color:
              v4w > 0
                ? "#34D399"
                : v4w < 0
                ? "#FB7185"
                : "#64748B",
          }}
        >
          {formatPercent(v4w)}
        </span>
        <span
          className="font-mono text-[9px] px-2 py-0.5 rounded"
          style={{
            color:
              v12w > 0
                ? "#34D399"
                : v12w < 0
                ? "#FB7185"
                : "#64748B",
            opacity: 0.7,
          }}
        >
          12w {formatPercent(v12w)}
        </span>
      </div>

      {/* Heat bar — thin vertical indicator */}
      {v4w > 0 && (
        <div className="w-1 h-10 rounded-full bg-white/[0.04] overflow-hidden shrink-0">
          <div
            className="w-full rounded-full transition-all duration-500"
            style={{
              height: `${Math.max(heat * 100, 8)}%`,
              backgroundColor: color,
              marginTop: "auto",
            }}
          />
        </div>
      )}
    </div>
  );
}

export default function HotNow({
  trends,
  colorMap = {},
  onKeywordClick,
}: HotNowProps) {
  // Sort by 4w velocity descending, take top 20
  const hotKeywords = useMemo(() => {
    return [...trends]
      .filter((t) => t.history.length >= 2)
      .sort((a, b) => b.velocity_4w - a.velocity_4w)
      .slice(0, 20);
  }, [trends]);

  const maxVelocity = hotKeywords.length > 0 ? hotKeywords[0].velocity_4w : 1;

  // Category breakdown — which categories are hottest
  const categoryHeat = useMemo(() => {
    const map = new Map<string, { total: number; count: number; top: string }>();
    for (const kw of hotKeywords) {
      const entry = map.get(kw.category) || { total: 0, count: 0, top: "" };
      entry.total += kw.velocity_4w;
      entry.count++;
      if (!entry.top) entry.top = kw.keyword;
      map.set(kw.category, entry);
    }
    return Array.from(map.entries())
      .map(([cat, data]) => ({
        category: cat,
        avgVelocity: data.total / data.count,
        count: data.count,
        topKeyword: data.top,
      }))
      .sort((a, b) => b.avgVelocity - a.avgVelocity);
  }, [hotKeywords]);

  if (hotKeywords.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        Not enough trend data yet to identify hot keywords.
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Category heat summary */}
      <div className="flex gap-2 mb-3 overflow-x-auto pb-1 shrink-0">
        {categoryHeat.slice(0, 6).map((ch) => {
          const color = colorMap[ch.category] || "#94a3b8";
          return (
            <div
              key={ch.category}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/[0.02] border border-white/[0.04] shrink-0"
            >
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: color }}
              />
              <span className="text-[10px] text-slate-400 capitalize">
                {ch.category.replace(/_/g, " ")}
              </span>
              <span className="text-[10px] font-mono text-emerald-400">
                +{ch.avgVelocity.toFixed(1)}%
              </span>
              <span className="text-[9px] text-slate-600">
                ({ch.count})
              </span>
            </div>
          );
        })}
      </div>

      {/* Hot keyword list */}
      <div className="flex-1 overflow-y-auto -mx-1 space-y-0.5">
        {hotKeywords.map((trend, i) => (
          <HotRow
            key={trend.keyword}
            trend={trend}
            rank={i + 1}
            color={colorMap[trend.category] || "#94a3b8"}
            maxVelocity={maxVelocity}
            onClick={() => onKeywordClick?.(trend.keyword)}
          />
        ))}
      </div>
    </div>
  );
}
