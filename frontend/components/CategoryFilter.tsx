"use client";

import { useState } from "react";
import type { CategoryInfo } from "@/lib/colors";
import { getCategoryColor } from "@/lib/colors";

interface CategoryFilterProps {
  categories: CategoryInfo[];
  colorMap: Record<string, string>;
  selected: string | null;
  onSelect: (category: string | null) => void;
  onAddCategory?: (name: string) => void;
}

export default function CategoryFilter({
  categories,
  colorMap,
  selected,
  onSelect,
  onAddCategory,
}: CategoryFilterProps) {
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");

  const handleAdd = () => {
    if (newName.trim() && onAddCategory) {
      onAddCategory(newName.trim().toLowerCase());
      setNewName("");
      setShowAdd(false);
    }
  };

  return (
    <div
      className="flex items-center gap-2 overflow-x-auto scrollbar-thin pb-1"
      role="tablist"
      style={{ scrollbarWidth: "thin", scrollbarColor: "rgba(255,255,255,0.1) transparent" }}
    >
      <button
        onClick={() => onSelect(null)}
        role="tab"
        aria-selected={selected === null}
        tabIndex={0}
        aria-label="Show all categories"
        className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all whitespace-nowrap shrink-0 ${
          selected === null
            ? "bg-white/10 text-white"
            : "bg-white/[0.03] text-slate-500 hover:text-slate-300"
        }`}
      >
        All
      </button>

      {categories.map((cat) => {
        const color = getCategoryColor(cat.name, colorMap);
        const isActive = selected === cat.name;
        return (
          <button
            key={cat.name}
            onClick={() => onSelect(isActive ? null : cat.name)}
            role="tab"
            aria-selected={isActive}
            tabIndex={0}
            aria-label={`Filter by ${cat.name}`}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all capitalize whitespace-nowrap shrink-0 ${
              isActive
                ? "text-white"
                : "bg-white/[0.03] text-slate-500 hover:text-slate-300"
            }`}
            style={
              isActive
                ? { backgroundColor: `${color}25`, color }
                : undefined
            }
          >
            <span
              className="inline-block w-2 h-2 rounded-full mr-1.5"
              style={{ backgroundColor: color }}
            />
            {cat.name}
          </button>
        );
      })}

      {onAddCategory && (
        <>
          {showAdd ? (
            <div className="flex items-center gap-1 shrink-0">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAdd()}
                placeholder="category name"
                className="bg-white/5 border border-white/10 rounded-full px-3 py-1 text-xs text-white placeholder:text-slate-600 w-32 focus:outline-none focus:border-white/20"
                autoFocus
              />
              <button
                onClick={handleAdd}
                className="px-2 py-1 rounded-full text-xs text-emerald-400 hover:bg-emerald-400/10 transition-colors"
              >
                Add
              </button>
              <button
                onClick={() => { setShowAdd(false); setNewName(""); }}
                className="px-2 py-1 rounded-full text-xs text-slate-500 hover:text-slate-300 transition-colors"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowAdd(true)}
              className="px-2.5 py-1.5 rounded-full text-xs text-slate-600 hover:text-slate-400 bg-white/[0.02] hover:bg-white/[0.05] border border-dashed border-white/10 transition-all shrink-0"
            >
              + Add
            </button>
          )}
        </>
      )}
    </div>
  );
}
