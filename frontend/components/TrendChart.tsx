"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { KeywordTrend } from "@/lib/types";

interface TrendChartProps {
  trends: KeywordTrend[];
  colorMap?: Record<string, string>;
}

/**
 * High-contrast categorical palette for distinguishing individual series
 * on a dark background. Each keyword gets its own color regardless of category.
 */
const SERIES_PALETTE = [
  "#22D3EE", // cyan-400
  "#34D399", // emerald-400
  "#F472B6", // pink-400
  "#FBBF24", // amber-400
  "#A78BFA", // violet-400
  "#FB923C", // orange-400
  "#38BDF8", // sky-400
  "#4ADE80", // green-400
];

export default function TrendChart({ trends }: TrendChartProps) {
  const dateMap = new Map<string, Record<string, number>>();

  // Top 6 by interest score (filtering already done upstream)
  const filtered = [...trends]
    .sort((a, b) => b.current_interest - a.current_interest)
    .slice(0, 6);

  // Assign each keyword a distinct color from the palette
  const keywordColorMap: Record<string, string> = {};
  filtered.forEach((trend, i) => {
    keywordColorMap[trend.keyword] = SERIES_PALETTE[i % SERIES_PALETTE.length];
  });

  for (const trend of filtered) {
    for (const point of trend.history) {
      if (!dateMap.has(point.date)) {
        dateMap.set(point.date, {});
      }
      dateMap.get(point.date)![trend.keyword] = point.interest_score;
    }
  }

  const chartData = Array.from(dateMap.entries())
    .map(([date, values]) => ({
      date,
      ...values,
    }))
    .sort((a, b) => a.date.localeCompare(b.date));

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        No trend data available yet. Run collectors to populate data.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          {filtered.map((trend) => {
            const color = keywordColorMap[trend.keyword];
            return (
              <linearGradient
                key={trend.keyword}
                id={`gradient-${trend.keyword.replace(/\s/g, "-")}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="5%" stopColor={color} stopOpacity={0.25} />
                <stop offset="95%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            );
          })}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
        <XAxis
          dataKey="date"
          stroke="#334155"
          tick={{ fontSize: 10, fontFamily: "JetBrains Mono", fill: "#64748b" }}
          tickFormatter={(d) => {
            const date = new Date(d);
            return `${date.getMonth() + 1}/${date.getDate()}`;
          }}
        />
        <YAxis
          stroke="#334155"
          tick={{ fontSize: 10, fontFamily: "JetBrains Mono", fill: "#64748b" }}
          domain={[0, 100]}
        />
        <Tooltip
          contentStyle={{
            background: "#12121c",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: "8px",
            fontFamily: "JetBrains Mono",
            fontSize: "11px",
            color: "#cbd5e1",
          }}
          labelFormatter={(d) => new Date(d).toLocaleDateString()}
        />
        <Legend
          wrapperStyle={{
            fontSize: "10px",
            fontFamily: "Outfit",
            color: "#94a3b8",
            paddingTop: "8px",
          }}
        />
        {filtered.map((trend) => {
          const color = keywordColorMap[trend.keyword];
          return (
            <Area
              key={trend.keyword}
              type="monotone"
              dataKey={trend.keyword}
              stroke={color}
              strokeWidth={2}
              fill={`url(#gradient-${trend.keyword.replace(/\s/g, "-")})`}
              dot={false}
              activeDot={{ r: 4, fill: color, stroke: color }}
            />
          );
        })}
      </AreaChart>
    </ResponsiveContainer>
  );
}
