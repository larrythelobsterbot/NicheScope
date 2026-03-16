"use client";

import { useState } from "react";

interface AdminPanelProps {
  onAddKeyword: (keyword: string, category: string) => void;
  onAddProduct: (asin: string, category: string) => void;
  onAddSupplier: (data: Record<string, string>) => void;
  categories: string[];
}

type ActiveForm = "keyword" | "product" | "supplier" | null;

export default function AdminPanel({
  onAddKeyword,
  onAddProduct,
  onAddSupplier,
  categories,
}: AdminPanelProps) {
  const [activeForm, setActiveForm] = useState<ActiveForm>(null);
  const [keyword, setKeyword] = useState("");
  const [category, setCategory] = useState(categories[0] || "");
  const [asin, setAsin] = useState("");
  const [supplierName, setSupplierName] = useState("");
  const [supplierRegion, setSupplierRegion] = useState("");
  const [supplierFocus, setSupplierFocus] = useState("");
  const [supplierUrl, setSupplierUrl] = useState("");

  const resetForms = () => {
    setKeyword("");
    setAsin("");
    setSupplierName("");
    setSupplierRegion("");
    setSupplierFocus("");
    setSupplierUrl("");
    setActiveForm(null);
  };

  const buttons = [
    { key: "keyword" as const, label: "Add Keyword", icon: "#" },
    { key: "product" as const, label: "Add ASIN", icon: "A" },
    { key: "supplier" as const, label: "Add Supplier", icon: "S" },
  ];

  return (
    <div className="space-y-4">
      {/* Quick-add buttons */}
      <div className="flex gap-2">
        {buttons.map((btn) => (
          <button
            key={btn.key}
            onClick={() => setActiveForm(activeForm === btn.key ? null : btn.key)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
              activeForm === btn.key
                ? "bg-white/10 text-white border border-white/15"
                : "bg-white/[0.03] text-slate-400 border border-white/5 hover:bg-white/[0.06] hover:text-white"
            }`}
          >
            <span className="w-5 h-5 rounded bg-white/10 flex items-center justify-center text-[10px] font-mono">
              {btn.icon}
            </span>
            {btn.label}
          </button>
        ))}
      </div>

      {/* Keyword form */}
      {activeForm === "keyword" && (
        <div className="p-4 rounded-lg bg-white/[0.02] border border-white/[0.05] space-y-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="keyword phrase..."
              className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-white/20"
              autoFocus
            />
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-36 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-white/20"
            >
              {categories.map((c) => (
                <option key={c} value={c} className="bg-[#12121c]">
                  {c}
                </option>
              ))}
            </select>
            <button
              onClick={() => {
                if (keyword.trim()) {
                  onAddKeyword(keyword.trim(), category);
                  resetForms();
                }
              }}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
            >
              Add
            </button>
          </div>
        </div>
      )}

      {/* Product/ASIN form */}
      {activeForm === "product" && (
        <div className="p-4 rounded-lg bg-white/[0.02] border border-white/[0.05] space-y-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={asin}
              onChange={(e) => setAsin(e.target.value.toUpperCase())}
              placeholder="ASIN (e.g. B0CXYZ1234)..."
              className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-white/20 font-mono"
              autoFocus
            />
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-36 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-white/20"
            >
              {categories.map((c) => (
                <option key={c} value={c} className="bg-[#12121c]">
                  {c}
                </option>
              ))}
            </select>
            <button
              onClick={() => {
                if (asin.trim()) {
                  onAddProduct(asin.trim(), category);
                  resetForms();
                }
              }}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
            >
              Add
            </button>
          </div>
        </div>
      )}

      {/* Supplier form */}
      {activeForm === "supplier" && (
        <div className="p-4 rounded-lg bg-white/[0.02] border border-white/[0.05] space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <input
              type="text"
              value={supplierName}
              onChange={(e) => setSupplierName(e.target.value)}
              placeholder="Supplier name..."
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-white/20"
              autoFocus
            />
            <input
              type="text"
              value={supplierRegion}
              onChange={(e) => setSupplierRegion(e.target.value)}
              placeholder="Region (e.g. Guangdong, China)..."
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-white/20"
            />
            <input
              type="text"
              value={supplierFocus}
              onChange={(e) => setSupplierFocus(e.target.value)}
              placeholder="Product focus..."
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-white/20"
            />
            <input
              type="text"
              value={supplierUrl}
              onChange={(e) => setSupplierUrl(e.target.value)}
              placeholder="Contact URL..."
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-white/20"
            />
          </div>
          <div className="flex justify-end">
            <button
              onClick={() => {
                if (supplierName.trim()) {
                  onAddSupplier({
                    name: supplierName.trim(),
                    region: supplierRegion.trim(),
                    product_focus: supplierFocus.trim(),
                    contact_url: supplierUrl.trim(),
                  });
                  resetForms();
                }
              }}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
            >
              Add Supplier
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
