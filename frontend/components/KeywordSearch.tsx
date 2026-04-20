"use client";

import { useRef, useEffect } from "react";

interface KeywordSearchProps {
  value: string;
  onChange: (query: string) => void;
  resultCount?: number;
}

export default function KeywordSearch({
  value,
  onChange,
  resultCount,
}: KeywordSearchProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  // Keyboard shortcut: "/" to focus search
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        e.key === "/" &&
        !e.ctrlKey &&
        !e.metaKey &&
        document.activeElement?.tagName !== "INPUT" &&
        document.activeElement?.tagName !== "TEXTAREA"
      ) {
        e.preventDefault();
        inputRef.current?.focus();
      }
      // Escape to clear and blur
      if (e.key === "Escape" && document.activeElement === inputRef.current) {
        onChange("");
        inputRef.current?.blur();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onChange]);

  return (
    <div className="relative">
      {/* Search icon */}
      <svg
        className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500 pointer-events-none"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
        />
      </svg>

      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder='Filter keywords\u2026  press "/" to focus'
        className="w-full pl-9 pr-20 py-2 rounded-lg text-sm bg-white/[0.03] border border-white/[0.05] text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-white/[0.12] focus:bg-white/[0.04] transition-all font-display"
        aria-label="Filter keywords"
      />

      {/* Right side: result count + clear button */}
      <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
        {value && resultCount !== undefined && (
          <span className="text-[10px] font-mono text-slate-500">
            {resultCount}
          </span>
        )}
        {value && (
          <button
            onClick={() => {
              onChange("");
              inputRef.current?.focus();
            }}
            className="text-slate-500 hover:text-slate-300 transition-colors p-0.5"
            aria-label="Clear search"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
        {!value && (
          <kbd className="text-[9px] font-mono text-slate-600 bg-white/[0.04] px-1.5 py-0.5 rounded border border-white/[0.06]">
            /
          </kbd>
        )}
      </div>
    </div>
  );
}
