"use client";

import { useState, useEffect, useRef } from "react";

interface QuickAddModalProps {
  open: boolean;
  onClose: () => void;
  onAdd: (keyword: string, category: string) => Promise<void>;
  categories: string[];
}

export default function QuickAddModal({ open, onClose, onAdd, categories }: QuickAddModalProps) {
  const [keyword, setKeyword] = useState("");
  const [category, setCategory] = useState(categories[0] || "");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setKeyword("");
      setSuccess(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  useEffect(() => {
    if (categories.length > 0 && !category) {
      setCategory(categories[0]);
    }
  }, [categories, category]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!keyword.trim() || !category) return;

    setSubmitting(true);
    try {
      await onAdd(keyword.trim(), category);
      setSuccess(true);
      setKeyword("");
      setTimeout(() => {
        setSuccess(false);
        inputRef.current?.focus();
      }, 1500);
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed bottom-24 right-6 z-50 w-80 animate-slide-up">
        <div className="glass-card p-5 border border-white/10 shadow-2xl">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-white">Quick Add Keyword</h3>
            <button
              onClick={onClose}
              className="text-slate-500 hover:text-white transition-colors text-lg leading-none"
            >
              x
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <input
                ref={inputRef}
                type="text"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="Enter keyword..."
                className="w-full px-3 py-2 rounded-lg bg-white/[0.05] border border-white/10 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-emerald-400/40 transition-colors"
              />
            </div>

            <div>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-white/[0.05] border border-white/10 text-sm text-white focus:outline-none focus:border-emerald-400/40 transition-colors"
              >
                {categories.map((c) => (
                  <option key={c} value={c} className="bg-[#12121a] text-white">
                    {c}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="submit"
              disabled={!keyword.trim() || submitting}
              className="w-full py-2 rounded-lg text-xs font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 disabled:opacity-40 transition-colors"
            >
              {submitting ? "Adding..." : success ? "Added!" : "Add to Watchlist"}
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
