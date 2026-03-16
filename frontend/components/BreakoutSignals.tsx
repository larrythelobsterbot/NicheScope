"use client";

import { Alert } from "@/lib/types";
import { severityToColor, alertTypeToIcon } from "@/lib/utils";

interface BreakoutSignalsProps {
  alerts: Alert[];
}

export default function BreakoutSignals({ alerts }: BreakoutSignalsProps) {
  if (alerts.length === 0) {
    return (
      <div className="text-slate-500 text-sm p-4">
        No breakout signals detected yet.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {alerts.map((alert, i) => (
        <div
          key={alert.id || i}
          className="glass-card p-3 flex items-start gap-3 animate-slide-up"
          style={{ animationDelay: `${i * 80}ms` }}
          role="article"
        >
          {/* Icon */}
          <span className="text-lg shrink-0 mt-0.5">
            {alertTypeToIcon(alert.type)}
          </span>

          {/* Content */}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              {/* Severity badge */}
              <span
                className="text-[10px] font-mono font-bold uppercase px-1.5 py-0.5 rounded"
                style={{
                  backgroundColor: `${severityToColor(alert.severity)}15`,
                  color: severityToColor(alert.severity),
                }}
              >
                {alert.severity}
              </span>
              {/* Type */}
              <span className="text-[10px] text-slate-500 uppercase">
                {alert.type.replace("_", " ")}
              </span>
            </div>

            {/* Message */}
            <p className="text-sm text-slate-300 leading-snug">
              {alert.message}
            </p>

            {/* Timestamp */}
            <p className="text-[10px] text-slate-600 mt-1 font-mono">
              {new Date(alert.sent_at).toLocaleString()}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
