"use client";

import { useEffect, useState } from "react";

// Decision-focused command-center header: replaces the vanity stat counts with
// metrics that answer "what should I act on", an auto-surfaced opportunity of
// the week, and a lifecycle distribution bar. Data from /api/insights.

interface Insights {
  emergingCount: number;
  vettedBreakouts: number;
  hottest: { category: string; median: number } | null;
  dataTrustPct: number | null;
  lifecycle: Record<string, number>;
  activeTotal: number;
  opportunity: {
    keyword: string;
    category: string;
    current_interest: number;
    velocity_4w: number;
    velocity_yoy: number | null;
    lifecycle: string;
    siblings: { keyword: string; current_interest: number; velocity_4w: number }[];
    overall_score: number | null;
    margin_score: number | null;
    sparkline: number[];
  } | null;
}

const LIFECYCLE = [
  { key: "emerging", label: "Emerging", color: "#a78bfa" },
  { key: "accelerating", label: "Accelerating", color: "#34d399" },
  { key: "peaking", label: "Peaking", color: "#fbbf24" },
  { key: "stable", label: "Stable", color: "#3b4252" },
  { key: "declining", label: "Declining", color: "#b04863" },
];

function Sparkline({ data }: { data: number[] }) {
  if (data.length < 2) return null;
  const w = 120, h = 48, max = Math.max(...data, 1), min = Math.min(...data);
  const range = max - min || 1;
  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * (h - 6) - 3}`)
    .join(" ");
  const last = pts.split(" ").pop()!.split(",");
  return (
    <svg width={w} height={h} className="shrink-0" aria-hidden>
      <polyline points={pts} fill="none" stroke="#34d399" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r="3.5" fill="#34d399" />
    </svg>
  );
}

function Kpi({ label, value, accent }: { label: string; value: React.ReactNode; accent?: string }) {
  return (
    <div className="glass-card p-5">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">{label}</div>
      <div className="font-mono text-lg font-bold text-slate-200" style={accent ? { color: accent } : undefined}>
        {value}
      </div>
    </div>
  );
}

export default function OpportunityHeader({
  onSelectCategory,
}: {
  onSelectCategory?: (category: string) => void;
}) {
  const [data, setData] = useState<Insights | null>(null);

  useEffect(() => {
    fetch("/api/insights")
      .then((r) => r.json())
      .then((d) => !d.error && setData(d))
      .catch(() => {});
  }, []);

  if (!data) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-7">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="glass-card p-5 h-[68px] animate-pulse" />
        ))}
      </div>
    );
  }

  const op = data.opportunity;
  const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ");

  return (
    <div className="mb-7 space-y-4 animate-slide-up">
      {/* Decision KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Kpi label="Emerging niches" value={<>{data.emergingCount} <span className="text-emerald-400 text-xs">rising</span></>} />
        <Kpi
          label="Hottest category"
          value={data.hottest ? <span className="text-sm">{cap(data.hottest.category)}</span> : "—"}
          accent="#34d399"
        />
        <Kpi label="Vetted breakouts" value={<>{data.vettedBreakouts} <span className="text-slate-500 text-xs">z&gt;2</span></>} />
        <Kpi
          label="Data trust"
          value={data.dataTrustPct !== null ? <>{data.dataTrustPct}% <span className="text-amber-400 text-xs">real</span></> : "—"}
        />
      </div>

      {/* Opportunity of the week */}
      {op && (
        <div className="glass-card p-6" style={{ borderColor: "rgba(52,211,153,0.25)" }}>
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="text-[10px] uppercase tracking-[0.1em] text-emerald-400 font-bold mb-1.5">
                ★ Opportunity of the week
              </div>
              <h2 className="font-display text-xl font-bold text-slate-100 truncate">{op.keyword}</h2>
              <div className="flex flex-wrap gap-1.5 mt-2.5">
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full" style={{ background: "rgba(52,211,153,0.13)", color: "#34d399" }}>
                  {cap(op.lifecycle)}
                </span>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-white/[0.05] text-slate-300">
                  {cap(op.category)}
                </span>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-white/[0.05] text-slate-300">
                  Interest {op.current_interest}
                </span>
                {op.velocity_yoy !== null && op.velocity_yoy > 50 && (
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full" style={{ background: "rgba(167,139,250,0.13)", color: "#a78bfa" }}>
                    YoY +{Math.round(op.velocity_yoy)}%
                  </span>
                )}
              </div>
              {op.siblings.length > 0 && (
                <div className="mt-3 text-xs text-slate-500">
                  Cluster:{" "}
                  <span className="text-slate-400">
                    {op.siblings.map((s) => s.keyword).slice(0, 4).join(" · ")}
                  </span>
                </div>
              )}
            </div>
            <div className="flex flex-col items-end gap-1 shrink-0">
              <Sparkline data={op.sparkline} />
              <span className="font-mono text-sm font-bold text-emerald-400">
                +{op.velocity_4w}% <span className="text-slate-500 text-[10px] font-normal">4w</span>
              </span>
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => onSelectCategory?.(op.category)}
              className="px-4 py-2 rounded-lg text-xs font-bold bg-emerald-500 text-emerald-950 hover:bg-emerald-400 transition-colors"
            >
              Explore {cap(op.category)} →
            </button>
            {op.overall_score !== null && (
              <span className="px-4 py-2 rounded-lg text-xs font-medium bg-white/[0.03] text-slate-400 border border-white/5">
                Niche score {op.overall_score}/100
              </span>
            )}
          </div>
        </div>
      )}

      {/* Lifecycle distribution */}
      <div className="glass-card p-5">
        <div className="flex items-center justify-between mb-2.5">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider">
            Keyword lifecycle · {data.activeTotal.toLocaleString()} active
          </div>
          <div className="text-[10px] text-slate-600">where your watchlist lives</div>
        </div>
        <div className="flex h-3.5 rounded-full overflow-hidden mb-2.5">
          {LIFECYCLE.map((l) => {
            const pct = data.activeTotal ? (data.lifecycle[l.key] / data.activeTotal) * 100 : 0;
            if (pct === 0) return null;
            return <div key={l.key} style={{ width: `${pct}%`, background: l.color }} title={`${l.label} ${data.lifecycle[l.key]}`} />;
          })}
        </div>
        <div className="flex gap-3.5 flex-wrap text-[11px]">
          {LIFECYCLE.map((l) => (
            <span key={l.key} className="text-slate-500">
              <span style={{ color: l.color }}>●</span> {l.label}{" "}
              {data.lifecycle[l.key].toLocaleString()}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
