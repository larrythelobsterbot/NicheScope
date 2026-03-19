"use client";

interface DataFreshnessProps {
  lastUpdated: string | null;
  totalDataPoints?: number;
}

function timeAgo(dateStr: string): { label: string; stale: boolean } {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const mins = Math.floor(diffMs / 60_000);
  const hours = Math.floor(diffMs / 3_600_000);
  const days = Math.floor(diffMs / 86_400_000);

  if (mins < 1) return { label: "just now", stale: false };
  if (mins < 60) return { label: `${mins}m ago`, stale: false };
  if (hours < 24) return { label: `${hours}h ago`, stale: hours > 12 };
  return { label: `${days}d ago`, stale: true };
}

export default function DataFreshness({
  lastUpdated,
  totalDataPoints,
}: DataFreshnessProps) {
  if (!lastUpdated) {
    return (
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <span className="w-2 h-2 rounded-full bg-slate-600" />
        <span>No data collected yet</span>
      </div>
    );
  }

  const { label, stale } = timeAgo(lastUpdated);

  return (
    <div className="flex items-center gap-2 text-xs">
      <span
        className={`w-2 h-2 rounded-full ${
          stale ? "bg-amber-400" : "bg-emerald-400"
        }`}
        style={{
          boxShadow: stale
            ? "0 0 6px rgba(251,191,36,0.4)"
            : "0 0 6px rgba(52,211,153,0.4)",
        }}
      />
      <span className={stale ? "text-amber-400/80" : "text-slate-400"}>
        Updated {label}
      </span>
      {totalDataPoints != null && (
        <span className="text-slate-600 ml-1">
          · {totalDataPoints.toLocaleString()} pts
        </span>
      )}
    </div>
  );
}
