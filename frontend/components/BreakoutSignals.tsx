"use client";

import { Alert } from "@/lib/types";
import { alertTypeToIcon } from "@/lib/utils";

interface BreakoutSignalsProps {
  alerts: Alert[];
}

/**
 * Determine if a breakout alert represents positive growth.
 * Checks the message for large positive percentages or growth keywords.
 */
function isPositiveBreakout(alert: Alert): boolean {
  const msg = alert.message || "";
  // Match patterns like "+7100.0%", "+4300.0%", "trending"
  const positiveMatch = msg.match(/\+\d+[\d.]*%/);
  if (positiveMatch) return true;
  if (alert.type === "breakout" || alert.type === "trend_shift") {
    // Unless message explicitly says "drop", "crash", "decline"
    if (/\b(drop|crash|decline|fall|plummet)\b/i.test(msg)) return false;
    return true;
  }
  return false;
}

interface BadgeConfig {
  label: string;
  bg: string;
  text: string;
  glow: boolean;
}

function getBadgeConfig(alert: Alert): BadgeConfig {
  const positive = isPositiveBreakout(alert);

  if (positive) {
    // Positive breakouts: green/gold "SURGE" or "HOT"
    const pct = alert.message?.match(/\+([\d.]+)%/);
    const value = pct ? parseFloat(pct[1]) : 0;

    if (value >= 1000) {
      return {
        label: "SURGE",
        bg: "rgba(52, 211, 153, 0.12)",
        text: "#34D399",
        glow: true,
      };
    }
    return {
      label: "HOT",
      bg: "rgba(251, 191, 36, 0.12)",
      text: "#FBBF24",
      glow: false,
    };
  }

  // Negative / error alerts keep red semantics
  switch (alert.severity) {
    case "critical":
      return {
        label: "CRITICAL",
        bg: "rgba(239, 68, 68, 0.12)",
        text: "#EF4444",
        glow: true,
      };
    case "warning":
      return {
        label: "WARNING",
        bg: "rgba(251, 191, 36, 0.10)",
        text: "#FBBF24",
        glow: false,
      };
    default:
      return {
        label: "INFO",
        bg: "rgba(96, 165, 250, 0.10)",
        text: "#60A5FA",
        glow: false,
      };
  }
}

export default function BreakoutSignals({ alerts }: BreakoutSignalsProps) {
  if (alerts.length === 0) {
    return (
      <div className="text-slate-600 text-sm p-4">
        No breakout signals detected yet.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {alerts.map((alert, i) => {
        const badge = getBadgeConfig(alert);
        return (
          <div
            key={alert.id || i}
            className="glass-card p-4 flex items-start gap-3 animate-slide-up"
            style={{ animationDelay: `${i * 80}ms` }}
            role="article"
          >
            {/* Icon */}
            <span className="text-base shrink-0 mt-0.5">
              {alertTypeToIcon(alert.type)}
            </span>

            {/* Content */}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 mb-1">
                {/* Semantic badge */}
                <span
                  className="text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded"
                  style={{
                    backgroundColor: badge.bg,
                    color: badge.text,
                    ...(badge.glow
                      ? { textShadow: `0 0 8px ${badge.text}40` }
                      : {}),
                  }}
                >
                  {badge.label}
                </span>
                <span className="text-[9px] text-slate-600 uppercase">
                  {alert.type.replace("_", " ")}
                </span>
              </div>

              <p className="text-sm text-slate-400 leading-snug">
                {alert.message}
              </p>

              <p className="text-[9px] text-slate-600 mt-1.5 font-mono">
                {new Date(alert.sent_at).toLocaleString()}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
