"use client";

import { NicheScore } from "@/lib/types";
import { formatPercent, scoreToColor } from "@/lib/utils";
import Sparkline from "./Sparkline";

interface NicheCardProps {
  rank: number;
  score: NicheScore;
  trendHistory?: number[];
  isSelected?: boolean;
  onClick?: () => void;
  colorMap?: Record<string, string>;
}

export default function NicheCard({
  rank,
  score,
  trendHistory = [],
  isSelected = false,
  onClick,
  colorMap = {},
}: NicheCardProps) {
  const color = colorMap[score.category] || "#94a3b8";
  const growth = score.trend_score > 50 ? score.trend_score - 50 : -(50 - score.trend_score);

  return (
    <div
      className={`glass-card glass-card-hover p-4 cursor-pointer relative overflow-hidden transition-all ${
        isSelected ? "ring-1" : ""
      }`}
      style={{
        borderLeftWidth: "3px",
        borderLeftColor: color,
        ...(isSelected ? { ringColor: color } : {}),
      }}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick?.(); } }}
      role="button"
      tabIndex={0}
      aria-label={`${score.category} niche, score ${score.overall_score.toFixed(0)} out of 100`}
      aria-selected={isSelected}
    >
      {/* Rank badge */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className="font-mono text-xs font-bold w-6 h-6 rounded-full flex items-center justify-center"
            style={{ backgroundColor: `${color}20`, color }}
          >
            {rank}
          </span>
          <h3 className="font-display font-semibold text-sm capitalize">
            {score.category}
          </h3>
        </div>
        <Sparkline data={trendHistory} color={color} width={60} height={20} />
      </div>

      {/* Score + Growth */}
      <div className="flex items-end justify-between">
        <div>
          <div className="font-mono text-2xl font-bold" style={{ color }}>
            {score.overall_score.toFixed(0)}
          </div>
          <div className="text-[10px] text-slate-500 uppercase tracking-wider">
            NicheScore
          </div>
        </div>
        <div className="text-right">
          <div
            className="font-mono text-sm font-medium"
            style={{ color: growth >= 0 ? "#34D399" : "#EF4444" }}
          >
            {formatPercent(growth * 2)}
          </div>
          <div className="text-[10px] text-slate-500">Growth</div>
        </div>
      </div>

      {/* Mini score bars */}
      <div className="mt-3 grid grid-cols-3 gap-1">
        {[
          { label: "TRD", value: score.trend_score },
          { label: "MRG", value: score.margin_score },
          { label: "SRC", value: score.sourcing_score },
        ].map((s) => (
          <div key={s.label}>
            <div className="text-[9px] text-slate-500 mb-0.5">{s.label}</div>
            <div className="h-1 rounded-full bg-white/5 overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${s.value}%`,
                  backgroundColor: scoreToColor(s.value),
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
