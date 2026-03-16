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
  selectedCategory?: string | null;
  colorMap?: Record<string, string>;
}

export default function TrendChart({ trends, selectedCategory, colorMap = {} }: TrendChartProps) {
  // Build unified timeline data
  const dateMap = new Map<string, Record<string, number>>();

  const filtered = selectedCategory
    ? trends.filter((t) => t.category === selectedCategory)
    : trends.slice(0, 6); // Top 6 keywords

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
            const color = colorMap[trend.category] || "#94a3b8";
            return (
              <linearGradient
                key={trend.keyword}
                id={`gradient-${trend.keyword.replace(/\s/g, "-")}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                <stop offset="95%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            );
          })}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis
          dataKey="date"
          stroke="#475569"
          tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }}
          tickFormatter={(d) => {
            const date = new Date(d);
            return `${date.getMonth() + 1}/${date.getDate()}`;
          }}
        />
        <YAxis
          stroke="#475569"
          tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }}
          domain={[0, 100]}
        />
        <Tooltip
          contentStyle={{
            background: "#12121c",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "8px",
            fontFamily: "JetBrains Mono",
            fontSize: "11px",
          }}
          labelFormatter={(d) => new Date(d).toLocaleDateString()}
        />
        <Legend
          wrapperStyle={{ fontSize: "11px", fontFamily: "Outfit" }}
        />
        {filtered.map((trend) => {
          const color = colorMap[trend.category] || "#94a3b8";
          return (
            <Area
              key={trend.keyword}
              type="monotone"
              dataKey={trend.keyword}
              stroke={color}
              strokeWidth={2}
              fill={`url(#gradient-${trend.keyword.replace(/\s/g, "-")})`}
              dot={false}
              activeDot={{ r: 4, fill: color }}
            />
          );
        })}
      </AreaChart>
    </ResponsiveContainer>
  );
}
