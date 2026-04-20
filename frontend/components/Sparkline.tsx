"use client";

import { useMemo } from "react";
import { generateSparklinePoints } from "@/lib/utils";

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  /** Optional: override the trend direction for color selection.
   *  When omitted, direction is inferred from the data shape. */
  trend?: "up" | "down" | "flat";
  strokeWidth?: number;
  /** Show a dashed baseline across the average. Default true. */
  showBaseline?: boolean;
}

const TREND_COLORS = {
  up: "#34D399",   // emerald-400
  down: "#FB7185", // rose-400
  flat: "#94A3B8", // slate-400
} as const;

/** Infer trend direction from data endpoints. */
function inferDirection(data: number[]): "up" | "down" | "flat" {
  if (data.length < 2) return "flat";
  const first = data[0];
  const last = data[data.length - 1];
  const range = Math.max(...data) - Math.min(...data) || 1;
  const changePct = Math.abs(last - first) / range;
  if (changePct < 0.08) return "flat";
  return last >= first ? "up" : "down";
}

export default function Sparkline({
  data,
  width = 80,
  height = 24,
  trend,
  strokeWidth = 1.5,
  showBaseline = true,
}: SparklineProps) {
  if (data.length < 2) return null;

  const direction = trend ?? inferDirection(data);
  const strokeColor = TREND_COLORS[direction];

  const points = generateSparklinePoints(data, width, height);

  // Baseline Y = average value mapped to SVG coords
  const avg = data.reduce((s, v) => s + v, 0) / data.length;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const baselineY = height - ((avg - min) / range) * height;

  const gradId = useMemo(
    () => `spark-${Math.random().toString(36).slice(2, 8)}`,
    []
  );

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      fill="none"
      className="inline-block"
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={strokeColor} stopOpacity={0.2} />
          <stop offset="100%" stopColor={strokeColor} stopOpacity={0} />
        </linearGradient>
      </defs>

      {/* Dashed baseline at average — always neutral gray */}
      {showBaseline && (
        <line
          x1={0}
          y1={baselineY}
          x2={width}
          y2={baselineY}
          stroke="#475569"
          strokeWidth={0.5}
          strokeDasharray="3 3"
          opacity={0.5}
        />
      )}

      {/* Area fill */}
      <polygon
        points={`0,${height} ${points} ${width},${height}`}
        fill={`url(#${gradId})`}
      />

      {/* Line */}
      <polyline
        points={points}
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* End dot */}
      <circle
        cx={width}
        cy={height - ((data[data.length - 1] - min) / range) * height}
        r={1.5}
        fill={strokeColor}
      />
    </svg>
  );
}
