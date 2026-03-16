"use client";

import { useState, useEffect } from "react";

interface CollectorData {
  last_run: string | null;
  schedule: string;
  requests_today: number;
  daily_limit: number | null;
  remaining: number | null;
  status: "healthy" | "warning" | "exhausted";
}

interface CollectorStatusData {
  collectors: Record<string, CollectorData>;
  total_keywords: number;
}

const STATUS_STYLES = {
  healthy: { text: "text-emerald-400", dot: "bg-emerald-400", label: "Healthy" },
  warning: { text: "text-yellow-400", dot: "bg-yellow-400", label: "Low Quota" },
  exhausted: { text: "text-red-400", dot: "bg-red-400", label: "Exhausted" },
};

const COLLECTOR_LABELS: Record<string, string> = {
  google_trends: "Google Trends",
  keepa: "Keepa",
  amazon_pa: "Amazon PA-API",
  tiktok: "TikTok Trends",
  similarweb: "SimilarWeb",
  alibaba: "Alibaba",
};

export default function CollectorStatus() {
  const [data, setData] = useState<CollectorStatusData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/collector-status")
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32">
        <div className="text-slate-500 animate-pulse text-sm">Loading collector status...</div>
      </div>
    );
  }

  if (!data || !data.collectors) {
    return (
      <div className="text-center text-slate-600 text-sm py-8">
        Could not load collector status
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="text-[10px] text-slate-500 px-1">
        Tracking {data.total_keywords} keywords
      </div>

      {Object.entries(data.collectors).map(([key, c]) => {
        const style = STATUS_STYLES[c.status] || STATUS_STYLES.healthy;
        const usagePct = c.daily_limit ? Math.round((c.requests_today / c.daily_limit) * 100) : null;

        return (
          <div
            key={key}
            className="p-3 rounded-lg bg-white/[0.02] border border-white/[0.05]"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className={`w-2 h-2 rounded-full ${style.dot}`} />
                <div>
                  <div className="text-sm text-white font-medium">
                    {COLLECTOR_LABELS[key] || key}
                  </div>
                  <div className="text-[10px] text-slate-600">{c.schedule}</div>
                </div>
              </div>

              <div className="text-right">
                <div className={`text-[10px] font-medium ${style.text}`}>{style.label}</div>
                {c.last_run && (
                  <div className="text-[10px] text-slate-600">
                    Last: {new Date(c.last_run).toLocaleDateString()}
                  </div>
                )}
              </div>
            </div>

            {c.daily_limit && (
              <div className="mt-2">
                <div className="flex justify-between text-[10px] text-slate-500 mb-1">
                  <span>{c.requests_today} / {c.daily_limit} today</span>
                  <span>{usagePct}%</span>
                </div>
                <div className="h-1 rounded-full bg-white/5 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      c.status === "exhausted"
                        ? "bg-red-400"
                        : c.status === "warning"
                        ? "bg-yellow-400"
                        : "bg-emerald-400/60"
                    }`}
                    style={{ width: `${Math.min(usagePct || 0, 100)}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
