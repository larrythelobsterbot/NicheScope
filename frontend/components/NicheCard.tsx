"use client";

import { NicheScore } from "@/lib/types";
import { scoreToColor } from "@/lib/utils";
import Sparkline from "./Sparkline";

interface NicheCardProps {
  rank: number;
  score: NicheScore;
  trendHistory?: number[];
  isSelected?: boolean;
  onClick?: () => void;
  colorMap?: Record<string, string>;
}

interface MicroBarProps {
  label: string;
  value: number;
}

function MicroBar({ label, value }: MicroBarProps) {
  const fillColor = scoreToColor(value);
  return (
    <div className="flex items-center gap-2">
      <span className="text-[9px] text-slate-500 font-mono w-6 shrink-0">
        {label}
      </span>
      <div className="flex-1 h-[2px] rounded-full bg-slate-800 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${Math.min(value, 100)}%`,
            backgroundColor: fillColor,
          }}
        />
      </div>
      <span
        className="text-[9px] font-mono w-5 text-right"
        style={{ color: fillColor }}
      >
        {value.toFixed(0)}
      </span>
    </div>
  );
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

  return (
    <div
      className={`glass-card glass-card-hover p-5 cursor-pointer relative overflow-hidden transition-all ${
        isSelected ? "ring-1" : ""
      }`}
      style={{
        borderLeftWidth: "3px",
        borderLeftColor: color,
        ...(isSelected ? { ringColor: color } : {}),
      }}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick?.();
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={`${score.category} niche, score ${score.overall_score.toFixed(0)} out of 100`}
      aria-selected={isSelected}
    >
      {/* Header: rank + name + sparkline */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span
            className="font-mono text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center"
            style={{ backgroundColor: `${color}18`, color }}
          >
            {rank}
          </span>
          <h3 className="font-display font-semibold text-sm capitalize text-slate-200">
            {score.category.replace(/_/g, " ")}
          </h3>
        </div>
        <Sparkline data={trendHistory} width={56} height={18} showBaseline={false} />
      </div>

      {/* Score */}
      <div className="mb-3">
        <div className="font-mono text-2xl font-bold tracking-tight" style={{ color }}>
          {score.overall_score.toFixed(0)}
        </div>
        <div className="text-[10px] text-slate-500 uppercase tracking-wider">
          NicheScore
        </div>
      </div>

      {/* Micro progress bars */}
      <div className="space-y-1.5">
        <MicroBar label="TRD" value={score.trend_score} />
        <MicroBar label="MRG" value={score.margin_score} />
        <MicroBar label="SRC" value={score.sourcing_score} />
      </div>
    </div>
  );
}
