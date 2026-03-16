"use client";

import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Legend,
  Tooltip,
} from "recharts";
import { NicheScore } from "@/lib/types";

interface NicheRadarProps {
  scores: NicheScore[];
  colorMap?: Record<string, string>;
}

const DIMENSION_LABELS: Record<string, string> = {
  trend_score: "Trend",
  margin_score: "Margin",
  competition_score: "Competition",
  sourcing_score: "Sourcing",
  content_score: "Content",
  repeat_purchase_score: "Repeat Purchase",
};

export default function NicheRadar({ scores, colorMap = {} }: NicheRadarProps) {
  if (scores.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        No niche scores available yet. Run the analyzer to generate scores.
      </div>
    );
  }

  // Transform data for Recharts radar
  const dimensions = Object.keys(DIMENSION_LABELS);
  const radarData = dimensions.map((dim) => {
    const entry: Record<string, string | number> = {
      dimension: DIMENSION_LABELS[dim],
    };
    for (const score of scores) {
      entry[score.category] = (score as any)[dim] || 0;
    }
    return entry;
  });

  return (
    <ResponsiveContainer width="100%" height="100%">
      <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
        <PolarGrid stroke="rgba(255,255,255,0.08)" />
        <PolarAngleAxis
          dataKey="dimension"
          tick={{
            fontSize: 11,
            fontFamily: "Outfit",
            fill: "#94a3b8",
          }}
        />
        <PolarRadiusAxis
          angle={30}
          domain={[0, 100]}
          tick={{ fontSize: 9, fontFamily: "JetBrains Mono", fill: "#475569" }}
        />
        {scores.slice(0, 3).map((score) => {
          const color = colorMap[score.category] || "#94a3b8";
          return (
            <Radar
              key={score.category}
              name={score.category.charAt(0).toUpperCase() + score.category.slice(1)}
              dataKey={score.category}
              stroke={color}
              fill={color}
              fillOpacity={0.15}
              strokeWidth={2}
            />
          );
        })}
        <Legend
          wrapperStyle={{ fontSize: "12px", fontFamily: "Outfit" }}
        />
        <Tooltip
          contentStyle={{
            background: "#12121c",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "8px",
            fontFamily: "JetBrains Mono",
            fontSize: "11px",
          }}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}
