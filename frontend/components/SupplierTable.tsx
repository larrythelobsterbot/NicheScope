"use client";

import { useState } from "react";
import { Supplier } from "@/lib/types";

interface SupplierTableProps {
  suppliers: Supplier[];
}

type SortKey = "quality_score" | "name" | "region" | "moq" | "lead_time";

export default function SupplierTable({ suppliers }: SupplierTableProps) {
  const [sortBy, setSortBy] = useState<SortKey>("quality_score");
  const [sortDesc, setSortDesc] = useState(true);

  const sorted = [...suppliers].sort((a, b) => {
    const dir = sortDesc ? -1 : 1;
    if (sortBy === "quality_score") return (a.quality_score - b.quality_score) * dir;
    const aVal = String(a[sortBy] || "");
    const bVal = String(b[sortBy] || "");
    return aVal.localeCompare(bVal) * dir;
  });

  const handleSort = (key: SortKey) => {
    if (sortBy === key) {
      setSortDesc(!sortDesc);
    } else {
      setSortBy(key);
      setSortDesc(true);
    }
  };

  const SortIcon = ({ active, desc }: { active: boolean; desc: boolean }) => (
    <span className={`ml-1 text-[10px] ${active ? "text-white" : "text-slate-600"}`}>
      {active ? (desc ? "▼" : "▲") : "▽"}
    </span>
  );

  if (suppliers.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        No supplier data available. Seed the database to see suppliers.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-white/5">
            <th
              className="pb-3 pr-4 cursor-pointer hover:text-slate-300 transition-colors"
              onClick={() => handleSort("name")}
            >
              Supplier
              <SortIcon active={sortBy === "name"} desc={sortDesc} />
            </th>
            <th
              className="pb-3 pr-4 cursor-pointer hover:text-slate-300 transition-colors"
              onClick={() => handleSort("region")}
            >
              Region
              <SortIcon active={sortBy === "region"} desc={sortDesc} />
            </th>
            <th className="pb-3 pr-4">Product Focus</th>
            <th className="pb-3 pr-4">Price Range</th>
            <th
              className="pb-3 pr-4 cursor-pointer hover:text-slate-300 transition-colors"
              onClick={() => handleSort("moq")}
            >
              MOQ
              <SortIcon active={sortBy === "moq"} desc={sortDesc} />
            </th>
            <th
              className="pb-3 pr-4 cursor-pointer hover:text-slate-300 transition-colors"
              onClick={() => handleSort("lead_time")}
            >
              Lead Time
              <SortIcon active={sortBy === "lead_time"} desc={sortDesc} />
            </th>
            <th
              className="pb-3 cursor-pointer hover:text-slate-300 transition-colors"
              onClick={() => handleSort("quality_score")}
            >
              Quality
              <SortIcon active={sortBy === "quality_score"} desc={sortDesc} />
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((supplier) => (
            <tr
              key={supplier.id}
              className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors"
            >
              <td className="py-3 pr-4">
                <div className="font-medium text-white">{supplier.name}</div>
                {supplier.certifications.length > 0 && (
                  <div className="flex gap-1 mt-1">
                    {supplier.certifications.map((cert) => (
                      <span
                        key={cert}
                        className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-slate-400"
                      >
                        {cert}
                      </span>
                    ))}
                  </div>
                )}
              </td>
              <td className="py-3 pr-4 text-slate-400">{supplier.region}</td>
              <td className="py-3 pr-4 text-slate-400 max-w-[180px] truncate">
                {supplier.product_focus}
              </td>
              <td className="py-3 pr-4 font-mono text-emerald-400">{supplier.price_range}</td>
              <td className="py-3 pr-4 font-mono text-slate-300">{supplier.moq}</td>
              <td className="py-3 pr-4 text-slate-400">{supplier.lead_time}</td>
              <td className="py-3">
                <div className="quality-bar">
                  {Array.from({ length: 10 }, (_, i) => (
                    <div
                      key={i}
                      className={`quality-segment ${i < supplier.quality_score ? "filled" : ""}`}
                      style={
                        i < supplier.quality_score
                          ? {
                              background:
                                supplier.quality_score >= 8
                                  ? "#34D399"
                                  : supplier.quality_score >= 6
                                  ? "#FBBF24"
                                  : "#EF4444",
                            }
                          : undefined
                      }
                    />
                  ))}
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5 font-mono">
                  {supplier.quality_score}/10
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
