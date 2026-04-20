"use client";

import { useState } from "react";

interface KeywordRow {
  id: number;
  keyword: string;
  category: string;
  subcategory: string | null;
  is_active: boolean;
}

interface KeywordTableProps {
  keywords: KeywordRow[];
  colorMap: Record<string, string>;
  onToggle: (keyword: string, active: boolean) => void;
  onAdd: (keyword: string, category: string) => void;
}

export default function KeywordTable({ keywords, colorMap, onToggle, onAdd }: KeywordTableProps) {
  const [newKeyword, setNewKeyword] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [filter, setFilter] = useState("");

  const filtered = keywords.filter(
    (k) =>
      k.keyword.toLowerCase().includes(filter.toLowerCase()) ||
      k.category.toLowerCase().includes(filter.toLowerCase()) ||
      (k.subcategory && k.subcategory.toLowerCase().includes(filter.toLowerCase()))
  );

  const handleAdd = () => {
    if (newKeyword.trim() && newCategory.trim()) {
      onAdd(newKeyword.trim(), newCategory.trim());
      setNewKeyword("");
      setNewCategory("");
    }
  };

  return (
    <div className="space-y-4">
      {/* Add form */}
      <div className="flex gap-2">
        <input
          type="text"
          value={newKeyword}
          onChange={(e) => setNewKeyword(e.target.value)}
          placeholder="New keyword..."
          className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-white/20"
        />
        <input
          type="text"
          value={newCategory}
          onChange={(e) => setNewCategory(e.target.value)}
          placeholder="Category..."
          className="w-32 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-white/20"
        />
        <button
          onClick={handleAdd}
          disabled={!newKeyword.trim() || !newCategory.trim()}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Add
        </button>
      </div>

      {/* Search filter */}
      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter keywords, categories, or subcategories..."
        className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-white/20"
      />

      {/* Table */}
      <div className="max-h-[400px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-500 uppercase tracking-wider border-b border-white/5 sticky top-0 bg-[#12121c]">
            <tr>
              <th className="text-left py-2 px-2">Keyword</th>
              <th className="text-left py-2 px-2">Category</th>
              <th className="text-left py-2 px-2">Subcategory</th>
              <th className="text-center py-2 px-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((kw) => (
              <tr key={`${kw.keyword}-${kw.category}`} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                <td className="py-2 px-2 text-white">{kw.keyword}</td>
                <td className="py-2 px-2">
                  <span
                    className="inline-flex items-center gap-1 text-xs capitalize"
                    style={{ color: colorMap[kw.category] || "#94A3B8" }}
                  >
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ backgroundColor: colorMap[kw.category] || "#94A3B8" }}
                    />
                    {kw.category.replace(/_/g, " ")}
                  </span>
                </td>
                <td className="py-2 px-2">
                  {kw.subcategory ? (
                    <span className="text-[10px] text-slate-400 px-2 py-0.5 rounded-full bg-white/[0.04] capitalize">
                      {kw.subcategory.replace(/_/g, " ")}
                    </span>
                  ) : (
                    <span className="text-slate-600 text-[10px]">&mdash;</span>
                  )}
                </td>
                <td className="py-2 px-2 text-center">
                  <button
                    onClick={() => onToggle(kw.keyword, !kw.is_active)}
                    className={`px-2.5 py-1 rounded-full text-[10px] font-medium transition-colors ${
                      kw.is_active
                        ? "bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30"
                        : "bg-red-500/20 text-red-400 hover:bg-red-500/30"
                    }`}
                  >
                    {kw.is_active ? "Active" : "Inactive"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="text-center text-slate-600 text-sm py-8">No keywords found</div>
        )}
      </div>
    </div>
  );
}
