"use client";

import { useState, useRef } from "react";

interface ClipboardImportProps {
  categories: string[];
  onImportComplete: () => void;
}

interface ParsedLine {
  keyword: string;
  subcategory: string;
}

interface ImportResult {
  added: number;
  skipped: number;
  newCategories: string[];
}

/**
 * Parse pasted text into keywords.
 * Accepts:
 *   - One keyword per line
 *   - CSV format: keyword, subcategory
 *   - Tab-separated: keyword\tsubcategory
 *   - Comma-separated list on one line
 */
function parseInput(text: string): ParsedLine[] {
  const lines = text
    .split(/\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.toLowerCase().startsWith("keyword"));

  const results: ParsedLine[] = [];

  for (const line of lines) {
    // Tab or comma separated: keyword [separator] subcategory
    let parts: string[];
    if (line.includes("\t")) {
      parts = line.split("\t").map((p) => p.trim());
    } else if (line.includes(",")) {
      // Could be "keyword, subcategory" or just a comma-separated list of keywords
      parts = line.split(",").map((p) => p.trim());
      // If more than 2 parts, treat each as a separate keyword (no subcategory)
      if (parts.length > 2) {
        for (const p of parts) {
          if (p) results.push({ keyword: p, subcategory: "" });
        }
        continue;
      }
    } else {
      parts = [line];
    }

    const keyword = parts[0]?.trim();
    const subcategory = parts[1]?.trim() || "";
    if (keyword) {
      results.push({ keyword, subcategory });
    }
  }

  return results;
}

export default function ClipboardImport({
  categories,
  onImportComplete,
}: ClipboardImportProps) {
  const [text, setText] = useState("");
  const [category, setCategory] = useState(categories[0] || "");
  const [defaultSubcategory, setDefaultSubcategory] = useState("");
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const parsed = text.trim() ? parseInput(text) : [];

  const handlePaste = async () => {
    try {
      const clipboard = await navigator.clipboard.readText();
      if (clipboard) {
        setText(clipboard);
      }
    } catch {
      // Clipboard API not available — user can paste manually
      textareaRef.current?.focus();
    }
  };

  const handleImport = async () => {
    if (parsed.length === 0 || !category) return;
    setImporting(true);
    setError(null);
    setResult(null);

    try {
      const keywords = parsed.map((p) => ({
        keyword: p.keyword,
        category,
        subcategory: p.subcategory || defaultSubcategory || undefined,
      }));

      const res = await fetch("/api/keywords/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keywords }),
      });

      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Import failed");
      } else {
        setResult(data);
        onImportComplete();
      }
    } catch {
      setError("Network error during import");
    } finally {
      setImporting(false);
    }
  };

  const handleReset = () => {
    setText("");
    setResult(null);
    setError(null);
    setDefaultSubcategory("");
  };

  return (
    <div className="space-y-4">
      {/* Category + subcategory selectors */}
      <div className="flex gap-3">
        <div className="flex-1">
          <label className="text-[10px] text-slate-500 uppercase tracking-wider mb-1 block">
            Category
          </label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-white/20"
          >
            {categories.map((c) => (
              <option key={c} value={c}>
                {c.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label className="text-[10px] text-slate-500 uppercase tracking-wider mb-1 block">
            Default Subcategory <span className="normal-case text-slate-600">(optional)</span>
          </label>
          <input
            type="text"
            value={defaultSubcategory}
            onChange={(e) => setDefaultSubcategory(e.target.value)}
            placeholder="e.g. serums, sunscreen..."
            className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-white/20"
          />
        </div>
      </div>

      {/* Paste area */}
      <div className="relative">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setResult(null);
            setError(null);
          }}
          placeholder={"Paste keywords here — one per line:\n\npdrn serum\nsalmon dna serum\nnumbuzin no 9\n\nOr with subcategories (comma/tab separated):\n\npdrn serum, serums\nkorean sunscreen, sunscreen"}
          rows={8}
          className="w-full bg-white/[0.03] border border-white/[0.06] rounded-xl px-4 py-3 text-sm text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-white/[0.12] resize-none font-mono leading-relaxed"
        />

        {/* Paste from clipboard button */}
        {!text && (
          <button
            onClick={handlePaste}
            className="absolute top-3 right-3 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-medium text-slate-400 bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] transition-all"
          >
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            Paste from clipboard
          </button>
        )}
      </div>

      {/* Preview */}
      {parsed.length > 0 && !result && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider">
              Preview — {parsed.length} keyword{parsed.length !== 1 ? "s" : ""} detected
            </span>
            <button
              onClick={handleReset}
              className="text-[10px] text-slate-500 hover:text-slate-300 transition-colors"
            >
              Clear
            </button>
          </div>

          <div className="max-h-[200px] overflow-y-auto rounded-lg border border-white/[0.04] divide-y divide-white/[0.03]">
            {parsed.slice(0, 50).map((p, i) => (
              <div
                key={i}
                className="flex items-center gap-3 px-3 py-1.5 text-xs"
              >
                <span className="text-slate-500 font-mono w-5 text-right shrink-0">
                  {i + 1}
                </span>
                <span className="text-slate-300 flex-1">{p.keyword}</span>
                {(p.subcategory || defaultSubcategory) && (
                  <span className="text-slate-500 text-[10px] px-2 py-0.5 rounded-full bg-white/[0.04]">
                    {p.subcategory || defaultSubcategory}
                  </span>
                )}
              </div>
            ))}
            {parsed.length > 50 && (
              <div className="px-3 py-1.5 text-[10px] text-slate-600">
                +{parsed.length - 50} more...
              </div>
            )}
          </div>
        </div>
      )}

      {/* Import button */}
      {parsed.length > 0 && !result && (
        <button
          onClick={handleImport}
          disabled={importing || !category}
          className="w-full py-2.5 rounded-lg text-xs font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 disabled:opacity-40 transition-colors"
        >
          {importing
            ? "Importing..."
            : `Add ${parsed.length} keywords to ${category.replace(/_/g, " ")}`}
        </button>
      )}

      {/* Error */}
      {error && (
        <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
          {error}
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 space-y-2">
          <div className="text-emerald-400 text-sm font-medium">
            Import complete
          </div>
          <div className="text-xs text-slate-300 space-y-1">
            <div>Added: {result.added}</div>
            {result.skipped > 0 && (
              <div>Skipped (duplicates): {result.skipped}</div>
            )}
            {result.newCategories.length > 0 && (
              <div>New categories: {result.newCategories.join(", ")}</div>
            )}
          </div>
          <button
            onClick={handleReset}
            className="text-[10px] text-slate-500 hover:text-white transition-colors underline underline-offset-2"
          >
            Import more
          </button>
        </div>
      )}

      {/* Help text */}
      {!text && (
        <div className="text-[10px] text-slate-600 space-y-1">
          <div>Accepts: one keyword per line, comma-separated, or tab-separated with subcategories</div>
          <div>Example formats:</div>
          <div className="font-mono text-slate-500 pl-2">
            pdrn serum<br />
            pdrn serum, serums<br />
            pdrn serum{"\t"}serums
          </div>
        </div>
      )}
    </div>
  );
}
