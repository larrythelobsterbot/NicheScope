"use client";

import { useState } from "react";
import type { PendingKeyword } from "@/lib/types";

interface PendingKeywordsProps {
  pending: PendingKeyword[];
  colorMap: Record<string, string>;
  onAction: (id: number, action: "approve" | "reject") => void;
}

type SourceFilter = "all" | "google_category" | "google_related" | "amazon_movers";

const SOURCE_LABELS: Record<string, string> = {
  all: "All",
  google_category: "Category Scan",
  google_related: "Related Queries",
  amazon_movers: "Amazon Movers",
};

export default function PendingKeywords({ pending, colorMap, onAction }: PendingKeywordsProps) {
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const filtered =
    sourceFilter === "all"
      ? pending
      : pending.filter((pk) => pk.source === sourceFilter);

  const sorted = [...filtered].sort(
    (a, b) => (b.relevance_score || 0) - (a.relevance_score || 0)
  );

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === sorted.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(sorted.map((pk) => pk.id)));
    }
  };

  const bulkAction = (action: "approve" | "reject") => {
    selected.forEach((id) => onAction(id, action));
    setSelected(new Set());
  };

  // Count by source for filter badges
  const sourceCounts: Record<string, number> = {};
  for (const pk of pending) {
    sourceCounts[pk.source] = (sourceCounts[pk.source] || 0) + 1;
  }

  if (pending.length === 0) {
    return (
      <div className="text-center text-slate-600 text-sm py-8">
        No pending keywords to review.
        <div className="text-[10px] mt-1 text-slate-700">
          Discovery mode finds new keywords automatically.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Source filter */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {(Object.keys(SOURCE_LABELS) as SourceFilter[]).map((key) => {
          const count = key === "all" ? pending.length : sourceCounts[key] || 0;
          if (key !== "all" && count === 0) return null;
          return (
            <button
              key={key}
              onClick={() => setSourceFilter(key)}
              className={`px-2.5 py-1 rounded-lg text-[10px] font-medium transition-all ${
                sourceFilter === key
                  ? "bg-white/10 text-white"
                  : "text-slate-500 hover:text-slate-300 bg-white/[0.02]"
              }`}
            >
              {SOURCE_LABELS[key]}
              <span className="ml-1 opacity-50">{count}</span>
            </button>
          );
        })}
      </div>

      {/* Bulk actions bar */}
      {selected.size > 0 && (
        <div className="flex items-center gap-2 p-2 rounded-lg bg-white/[0.03] border border-white/5">
          <span className="text-[10px] text-slate-400">{selected.size} selected</span>
          <button
            onClick={() => bulkAction("approve")}
            className="px-3 py-1 rounded text-[10px] font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
          >
            Approve All
          </button>
          <button
            onClick={() => bulkAction("reject")}
            className="px-3 py-1 rounded text-[10px] font-medium bg-red-500/15 text-red-400 hover:bg-red-500/25 transition-colors"
          >
            Reject All
          </button>
          <button
            onClick={() => setSelected(new Set())}
            className="px-2 py-1 text-[10px] text-slate-500 hover:text-white transition-colors ml-auto"
          >
            Clear
          </button>
        </div>
      )}

      {/* Select all checkbox */}
      <div className="flex items-center gap-2 px-1">
        <input
          type="checkbox"
          checked={selected.size === sorted.length && sorted.length > 0}
          onChange={toggleAll}
          className="rounded border-white/20 bg-white/5 text-emerald-400 focus:ring-0 focus:ring-offset-0"
        />
        <span className="text-[10px] text-slate-500">Select all ({sorted.length})</span>
      </div>

      {/* Keyword list */}
      <div className="space-y-2 max-h-[400px] overflow-y-auto">
        {sorted.map((pk) => (
          <div
            key={pk.id}
            className="flex items-center gap-2 p-3 rounded-lg bg-white/[0.02] border border-white/[0.05] hover:bg-white/[0.04] transition-colors"
          >
            <input
              type="checkbox"
              checked={selected.has(pk.id)}
              onChange={() => toggleSelect(pk.id)}
              className="rounded border-white/20 bg-white/5 text-emerald-400 focus:ring-0 focus:ring-offset-0"
            />

            <div className="flex-1 min-w-0">
              <div className="text-sm text-white font-medium truncate">{pk.keyword}</div>
              <div className="flex items-center gap-3 mt-1">
                <span
                  className="text-[10px] capitalize"
                  style={{ color: colorMap[pk.suggested_category] || "#94A3B8" }}
                >
                  {pk.suggested_category}
                </span>
                <span className="text-[10px] text-slate-600">
                  via {pk.source?.replace("_", " ") || "unknown"}
                </span>
                {pk.parent_keyword && (
                  <span className="text-[10px] text-slate-600">
                    from: {pk.parent_keyword}
                  </span>
                )}
                {pk.relevance_score > 0 && (
                  <span className="text-[10px] text-slate-500">
                    score: {pk.relevance_score.toFixed(2)}
                  </span>
                )}
              </div>
            </div>

            <div className="flex items-center gap-1.5 ml-3">
              <button
                onClick={() => onAction(pk.id, "approve")}
                className="px-3 py-1.5 rounded-lg text-[10px] font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
              >
                Approve
              </button>
              <button
                onClick={() => onAction(pk.id, "reject")}
                className="px-3 py-1.5 rounded-lg text-[10px] font-medium bg-red-500/15 text-red-400 hover:bg-red-500/25 transition-colors"
              >
                Reject
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
