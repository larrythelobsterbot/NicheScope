"use client";

import { Lifecycle } from "@/lib/types";

const STYLES: Record<Lifecycle, { label: string; color: string; bg: string }> = {
  emerging: { label: "Emerging", color: "#C084FC", bg: "rgba(192, 132, 252, 0.1)" },
  accelerating: { label: "Accelerating", color: "#34D399", bg: "rgba(52, 211, 153, 0.1)" },
  peaking: { label: "Peaking", color: "#FBBF24", bg: "rgba(251, 191, 36, 0.1)" },
  declining: { label: "Declining", color: "#FB7185", bg: "rgba(251, 113, 133, 0.1)" },
  stable: { label: "Stable", color: "#64748B", bg: "rgba(100, 116, 139, 0.08)" },
};

export default function LifecycleBadge({
  lifecycle,
  isSeasonal = false,
  showStable = false,
}: {
  lifecycle?: Lifecycle | string | null;
  isSeasonal?: boolean;
  showStable?: boolean;
}) {
  const stage = (lifecycle ?? "stable") as Lifecycle;
  const style = STYLES[stage] ?? STYLES.stable;
  const showStage = stage !== "stable" || showStable;

  if (!showStage && !isSeasonal) return null;

  return (
    <span className="inline-flex items-center gap-1 shrink-0">
      {showStage && (
        <span
          className="text-[9px] font-medium px-1.5 py-0.5 rounded-full"
          style={{ color: style.color, backgroundColor: style.bg }}
        >
          {style.label}
        </span>
      )}
      {isSeasonal && (
        <span
          className="text-[9px] font-medium px-1.5 py-0.5 rounded-full"
          style={{ color: "#38BDF8", backgroundColor: "rgba(56, 189, 248, 0.1)" }}
          title="Spike matches the same period last year — likely an annual pattern, not a new trend"
        >
          Seasonal
        </span>
      )}
    </span>
  );
}
