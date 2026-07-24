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
  search: string;
  onSearchChange: (value: string) => void;
  page: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export default function KeywordTable({
  keywords,
  colorMap,
  onToggle,
  onAdd,
  search,
  onSearchChange,
  page,
  total,
  totalPages,
  onPageChange,
}: KeywordTableProps) {
  const [newKeyword, setNewKeyword] = useState("");
  const [newCategory, setNewCategory] = useState("");

  const handleAdd = () => {
    if (newKeyword.trim() && newCategory.trim()) {
      onAdd(newKeyword.trim(), newCategory.trim());
      setNewKeyword("");
      setNewCategory("");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <input
          type="text"
          value={newKeyword}
          onChange={(event) => setNewKeyword(event.target.value)}
          placeholder="New keyword..."
          className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-white/20"
        />
        <input
          type="text"
          value={newCategory}
          onChange={(event) => setNewCategory(event.target.value)}
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

      <input
        type="search"
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
        placeholder="Search all keywords, categories, or subcategories..."
        className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-white/20"
      />

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
            {keywords.map((keyword) => (
              <tr key={keyword.id} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                <td className="py-2 px-2 text-white">{keyword.keyword}</td>
                <td className="py-2 px-2">
                  <span
                    className="inline-flex items-center gap-1 text-xs capitalize"
                    style={{ color: colorMap[keyword.category] || "#94A3B8" }}
                  >
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ backgroundColor: colorMap[keyword.category] || "#94A3B8" }}
                    />
                    {keyword.category.replace(/_/g, " ")}
                  </span>
                </td>
                <td className="py-2 px-2">
                  {keyword.subcategory ? (
                    <span className="text-[10px] text-slate-400 px-2 py-0.5 rounded-full bg-white/[0.04] capitalize">
                      {keyword.subcategory.replace(/_/g, " ")}
                    </span>
                  ) : (
                    <span className="text-slate-600 text-[10px]">&mdash;</span>
                  )}
                </td>
                <td className="py-2 px-2 text-center">
                  <button
                    onClick={() => onToggle(keyword.keyword, !keyword.is_active)}
                    className={`px-2.5 py-1 rounded-full text-[10px] font-medium transition-colors ${
                      keyword.is_active
                        ? "bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30"
                        : "bg-red-500/20 text-red-400 hover:bg-red-500/30"
                    }`}
                  >
                    {keyword.is_active ? "Active" : "Inactive"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {keywords.length === 0 && (
          <div className="text-center text-slate-600 text-sm py-8">No keywords found</div>
        )}
      </div>

      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>
          {total.toLocaleString()} result{total === 1 ? "" : "s"} · page {page} of {totalPages}
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
