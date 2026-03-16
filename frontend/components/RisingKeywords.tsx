"use client";

import { formatPercent } from "@/lib/utils";

interface RisingKeyword {
  keyword: string;
  category: string;
  interest_score: number;
  change_pct: number;
}

interface RisingKeywordsProps {
  keywords: RisingKeyword[];
  colorMap?: Record<string, string>;
}

export default function RisingKeywords({ keywords, colorMap = {} }: RisingKeywordsProps) {
  if (keywords.length === 0) {
    return (
      <div className="text-slate-500 text-sm p-4">
        No rising keywords detected yet.
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {keywords.map((kw, i) => {
        const color = colorMap[kw.category] || "#94a3b8";
        const isRising = kw.change_pct > 0;

        return (
          <div
            key={kw.keyword}
            className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-white/[0.02] transition-colors"
            style={{ animationDelay: `${i * 50}ms` }}
          >
            <div className="flex items-center gap-3 min-w-0">
              {/* Rank indicator */}
              <span className="text-xs font-mono text-slate-500 w-5 text-right shrink-0">
                {i + 1}
              </span>

              {/* Category dot */}
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: color }}
              />

              {/* Keyword */}
              <span className="text-sm text-slate-200 truncate">{kw.keyword}</span>
            </div>

            <div className="flex items-center gap-3 shrink-0 ml-3">
              {/* Interest score */}
              <span className="text-xs font-mono text-slate-500">
                {kw.interest_score}
              </span>

              {/* Change badge */}
              <span
                className="text-xs font-mono font-medium px-2 py-0.5 rounded-full"
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
          </div>
        );
      })}
    </div>
  );
}
