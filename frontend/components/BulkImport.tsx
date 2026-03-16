"use client";

import { useState, useRef, useCallback } from "react";

interface ImportResult {
  added: number;
  skipped: number;
  newCategories: string[];
}

interface BulkImportProps {
  onImportComplete: () => void;
}

export default function BulkImport({ onImportComplete }: BulkImportProps) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string[][]>([]);
  const [headers, setHeaders] = useState<string[]>([]);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const parseCSV = useCallback((text: string) => {
    const lines = text.split("\n").filter((l) => l.trim());
    if (lines.length < 2) return;

    const hdrs = lines[0].split(",").map((h) => h.trim());
    setHeaders(hdrs);

    const rows = lines.slice(1, 21).map((line) => line.split(",").map((c) => c.trim()));
    setPreview(rows);
  }, []);

  const handleFile = useCallback(
    (f: File) => {
      if (!f.name.endsWith(".csv")) {
        setError("Only .csv files are accepted");
        return;
      }
      setFile(f);
      setResult(null);
      setError(null);

      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result as string;
        parseCSV(text);
      };
      reader.readAsText(f);
    },
    [parseCSV]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      if (e.dataTransfer.files?.[0]) {
        handleFile(e.dataTransfer.files[0]);
      }
    },
    [handleFile]
  );

  const handleImport = async () => {
    if (!file) return;
    setImporting(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/import", { method: "POST", body: formData });
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

  const downloadTemplate = () => {
    const csv = [
      "category,keyword,subcategory,priority",
      "beauty,nail stickers,nail art,high",
      "beauty,press on nails,,medium",
      "jewelry,septum rings,body jewelry,high",
      "travel,packing cubes,,medium",
      "home,pendant lights,decor,low",
    ].join("\n");

    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "nichescope_keywords_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      {/* Dropzone */}
      <div
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
          dragActive
            ? "border-emerald-400/50 bg-emerald-400/5"
            : file
            ? "border-emerald-400/30 bg-white/[0.02]"
            : "border-white/10 hover:border-white/20 bg-white/[0.01]"
        }`}
        onDragEnter={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
        {file ? (
          <div>
            <div className="text-emerald-400 text-sm font-medium">{file.name}</div>
            <div className="text-[10px] text-slate-500 mt-1">
              {preview.length} rows previewed | Click or drop to replace
            </div>
          </div>
        ) : (
          <div>
            <div className="text-slate-400 text-sm">Drop a .csv file here or click to browse</div>
            <div className="text-[10px] text-slate-600 mt-1">
              Required columns: category, keyword
            </div>
          </div>
        )}
      </div>

      {/* Template download */}
      <button
        onClick={downloadTemplate}
        className="text-[10px] text-slate-500 hover:text-emerald-400 transition-colors underline underline-offset-2"
      >
        Download template CSV
      </button>

      {/* Preview table */}
      {preview.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-white/5">
                {headers.map((h, i) => (
                  <th key={i} className="text-left py-2 px-2 text-slate-500 font-medium uppercase tracking-wider">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.map((row, i) => (
                <tr key={i} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                  {row.map((cell, j) => (
                    <td key={j} className="py-1.5 px-2 text-slate-300">
                      {cell || <span className="text-slate-600">-</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {preview.length >= 20 && (
            <div className="text-[10px] text-slate-600 mt-1 px-2">
              Showing first 20 rows...
            </div>
          )}
        </div>
      )}

      {/* Import button */}
      {file && !result && (
        <button
          onClick={handleImport}
          disabled={importing}
          className="w-full py-2.5 rounded-lg text-xs font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 disabled:opacity-50 transition-colors"
        >
          {importing ? "Importing..." : `Import ${preview.length} keywords`}
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
          <div className="text-emerald-400 text-sm font-medium">Import complete</div>
          <div className="text-xs text-slate-300 space-y-1">
            <div>Added: {result.added}</div>
            <div>Skipped (duplicates): {result.skipped}</div>
            {result.newCategories.length > 0 && (
              <div>New categories: {result.newCategories.join(", ")}</div>
            )}
          </div>
          <button
            onClick={() => {
              setFile(null);
              setPreview([]);
              setHeaders([]);
              setResult(null);
            }}
            className="text-[10px] text-slate-500 hover:text-white transition-colors underline underline-offset-2"
          >
            Import another file
          </button>
        </div>
      )}
    </div>
  );
}
