"use client";

import { formatPercent } from "@/lib/utils";
import Sparkline from "./Sparkline";

interface RisingKeyword {
  keyword: string;
  category: string;
  interest_score: number;
  change_pct: number;
  history?: number[];
}

interface RisingKeywordsProps {
  keywords: RisingKeyword[];
  colorMap?: Record<string, string>;
  trendMap?: Record<string, number[]>;
}

export default function RisingKeywords({
  keywords,
  colorMap = {},
  trendMap = {},
}: RisingKeywordsProps) {
  if (keywords.length === 0) {
    return (
      <div className="text-slate-500 text-sm p-4">
        No rising keywords detected yet.
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      {keywords.map((kw, i) => {
        const color = colorMap[kw.category] || "#94a3b8";
        const isRising = kw.change_pct > 0;
        const sparkData = trendMap[kw.keyword] || kw.history || [];

        return (
          <div
            key={kw.keyword}
            className="flex items-center gap-3 py-2.5 px-3 rounded-lg hover:bg-white/[0.03] transition-colors"
            style={{ animationDelay: `${i * 50}ms` }}
          >
            {/* Rank */}
            <span className="text-[10px] font-mono text-slate-600 w-4 text-right shrink-0">
              {i + 1}
            </span>

            {/* Category dot */}
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: color }}
            />

            {/* Keyword name - full, no truncation */}
            <span className="text-sm text-slate-300 font-medium flex-1 min-w-0 break-words leading-tight">
              {kw.keyword}
            </span>

            {/* Mini sparkline */}
            {sparkData.length >= 2 && (
              <span className="shrink-0">
                <Sparkline
                  data={sparkData}
                  width={48}
                  height={16}
                  color={color}
                  strokeWidth={1}
                />
              </span>
            )}

            {/* Change badge */}
            <span
              className="text-[11px] font-mono font-medium px-2 py-0.5 rounded-full shrink-0"
              style={{
                backgroundColor: isRising
                  ? "rgba(52, 211, 153, 0.1)"
                  : "rgba(239, 68, 68, 0.1)",
                color: isRising ? "#34D399" : "#EF4444",
              }}
            >
              {formatPercent(kw.change_pct)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
