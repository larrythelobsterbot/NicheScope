"use client";

import { generateSparklinePoints } from "@/lib/utils";

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  strokeWidth?: number;
}

export default function Sparkline({
  data,
  width = 80,
  height = 24,
  color = "#34D399",
  strokeWidth = 1.5,
}: SparklineProps) {
  if (data.length < 2) return null;

  const points = generateSparklinePoints(data, width, height);
  const trend = data[data.length - 1] >= data[0] ? color : "#EF4444";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      fill="none"
      className="inline-block"
    >
      {/* Gradient fill under the line */}
      <defs>
        <linearGradient id={`spark-grad-${color}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={trend} stopOpacity={0.3} />
          <stop offset="100%" stopColor={trend} stopOpacity={0} />
        </linearGradient>
      </defs>
      {/* Area fill */}
      <polygon
        points={`0,${height} ${points} ${width},${height}`}
        fill={`url(#spark-grad-${color})`}
      />
      {/* Line */}
      <polyline
        points={points}
        stroke={trend}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* End dot */}
      {data.length > 0 && (
        <circle
          cx={width}
          cy={
            height -
            ((data[data.length - 1] - Math.min(...data)) /
              (Math.max(...data) - Math.min(...data) || 1)) *
              height
          }
          r={2}
          fill={trend}
        />
      )}
    </svg>
  );
}
