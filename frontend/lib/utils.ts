export function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toFixed(0);
}

export function formatPercent(n: number): string {
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

export function formatCurrency(n: number): string {
  return `$${n.toFixed(2)}`;
}

export function velocityToSize(velocity: number, min = 14, max = 48): number {
  // Map velocity to font size for word cloud
  const clamped = Math.max(0, Math.min(500, Math.abs(velocity)));
  return min + (clamped / 500) * (max - min);
}

export function scoreToColor(score: number): string {
  if (score >= 80) return "#34D399"; // emerald-400 — strong
  if (score >= 50) return "#FBBF24"; // amber-400  — moderate
  return "#FB7185";                  // rose-400   — weak
}

export function severityToColor(severity: string): string {
  switch (severity) {
    case "critical":
      return "#EF4444";
    case "warning":
      return "#FBBF24";
    default:
      return "#60A5FA";
  }
}

export function severityToIcon(severity: string): string {
  switch (severity) {
    case "critical":
      return "🔥";
    case "warning":
      return "⚠️";
    default:
      return "ℹ️";
  }
}

export function alertTypeToIcon(type: string): string {
  switch (type) {
    case "breakout":
      return "📈";
    case "price_drop":
      return "📉";
    case "stock_out":
      return "🛑";
    case "trend_shift":
      return "🌊";
    default:
      return "📊";
  }
}

export function generateSparklinePoints(
  data: number[],
  width: number,
  height: number
): string {
  if (data.length < 2) return "";

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  return data
    .map((val, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((val - min) / range) * height;
      return `${x},${y}`;
    })
    .join(" ");
}
