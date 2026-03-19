"use client";

import { KeywordTrend } from "@/lib/types";
import { formatPercent } from "@/lib/utils";
import Sparkline from "./Sparkline";

interface SparklineGridProps {
  trends: KeywordTrend[];
  selectedCategory?: string | null;
  colorMap?: Record<string, string>;
}

export default function SparklineGrid({
  trends,
  selectedCategory,
  colorMap = {},
}: SparklineGridProps) {
  const filtered = selectedCategory
    ? trends.filter((t) => t.category === selectedCategory)
    : trends;

  // Sort by current interest descending, take top 12
  const sorted = [...filtered]
    .sort((a, b) => b.current_interest - a.current_interest)
    .slice(0, 12);

  if (sorted.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        No trend data available yet. Run collectors to populate data.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 h-full overflow-y-auto pr-1">
      {sorted.map((trend) => {
        const color = colorMap[trend.category] || "#94a3b8";
        const history = trend.history
          .slice()
          .sort((a, b) => a.date.localeCompare(b.date))
          .map((h) => h.interest_score);

        const velocityColor = trend.velocity_4w >= 0 ? "#34D399" : "#EF4444";

        return (
          <div
            key={trend.keyword}
            className="glass-card p-3 flex flex-col justify-between"
          >
            {/* Keyword name + category dot */}
            <div className="flex items-start gap-2 mb-2">
              <span
                className="w-2 h-2 rounded-full mt-1 shrink-0"
                style={{ backgroundColor: color }}
              />
              <span className="text-xs text-slate-300 font-medium leading-tight line-clamp-2">
                {trend.keyword}
              </span>
            </div>

            {/* Sparkline */}
            <div className="mb-2">
              <Sparkline
                data={history}
                width={140}
                height={32}
                color={color}
                strokeWidth={1.5}
              />
            </div>

            {/* Stats row */}
            <div className="flex items-center justify-between">
              <span className="font-mono text-sm font-bold" style={{ color }}>
                {trend.current_interest}
              </span>
              <span
                className="font-mono text-[11px] font-medium"
                style={{ color: velocityColor }}
              >
                {formatPercent(trend.velocity_4w)}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
