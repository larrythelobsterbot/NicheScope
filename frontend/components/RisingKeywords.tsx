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
      <div className="text-slate-600 text-sm p-4">
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
            className="flex items-center gap-3 py-2.5 px-3 rounded-lg hover:bg-white/[0.02] transition-colors"
          >
            {/* Rank */}
            <span className="text-[10px] font-mono text-slate-600 w-4 text-right shrink-0">
              {i + 1}
            </span>

            {/* Category dot */}
            <span
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{ backgroundColor: color }}
            />

            {/* Keyword name */}
            <span className="text-sm text-slate-400 font-medium flex-1 min-w-0 break-words leading-tight">
              {kw.keyword}
            </span>

            {/* Mini sparkline */}
            {sparkData.length >= 2 && (
              <span className="shrink-0">
                <Sparkline
                  data={sparkData}
                  width={48}
                  height={16}
                  trend={kw.change_pct > 0 ? "up" : kw.change_pct < 0 ? "down" : "flat"}
                  strokeWidth={1}
                  showBaseline={false}
                />
              </span>
            )}

            {/* Change badge */}
            <span
              className="text-[10px] font-mono font-medium px-2 py-0.5 rounded-full shrink-0"
              style={{
                backgroundColor: isRising
                  ? "rgba(52, 211, 153, 0.08)"
                  : "rgba(251, 113, 133, 0.08)",
                color: isRising ? "#34D399" : "#FB7185",
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
