"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import type { PendingKeyword } from "@/lib/types";
import { getCategoryColorMap, type CategoryInfo } from "@/lib/colors";
import CategoryFilter from "@/components/CategoryFilter";
import KeywordTable from "@/components/KeywordTable";
import PendingKeywords from "@/components/PendingKeywords";
import CollectorStatus from "@/components/CollectorStatus";
import AdminPanel from "@/components/AdminPanel";
import BulkImport from "@/components/BulkImport";

type AdminTab = "keywords" | "pending" | "collectors" | "import";

interface KeywordRow {
  id: number;
  keyword: string;
  category: string;
  subcategory: string | null;
  is_active: boolean;
}

export default function AdminPage() {
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [colorMap, setColorMap] = useState<Record<string, string>>({});
  const [keywords, setKeywords] = useState<KeywordRow[]>([]);
  const [pending, setPending] = useState<PendingKeyword[]>([]);
  const [activeTab, setActiveTab] = useState<AdminTab>("keywords");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [catRes, pendingRes] = await Promise.all([
        fetch("/api/categories"),
        fetch("/api/pending"),
      ]);

      const catData = await catRes.json();
      const pendingData = await pendingRes.json();

      const cats = catData.categories || [];
      setCategories(cats);
      setColorMap(getCategoryColorMap(cats));
      setPending(pendingData.pending || []);

      // Fetch all keywords (active and inactive) for the keyword table
      // We use a special param to get all keywords including inactive
      const kwRes = await fetch("/api/keywords?limit=500");
      const kwData = await kwRes.json();
      setKeywords(kwData.keywords || []);
    } catch (error) {
      console.error("Failed to fetch admin data:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAddKeyword = async (keyword: string, category: string) => {
    try {
      await fetch("/api/keywords", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyword, category }),
      });
      fetchData();
    } catch (error) {
      console.error("Failed to add keyword:", error);
    }
  };

  const handleToggleKeyword = async (keyword: string, active: boolean) => {
    try {
      await fetch("/api/keywords", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyword, is_active: active }),
      });
      fetchData();
    } catch (error) {
      console.error("Failed to toggle keyword:", error);
    }
  };

  const handlePendingAction = async (id: number, action: "approve" | "reject") => {
    try {
      await fetch("/api/pending", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, action }),
      });
      fetchData();
    } catch (error) {
      console.error("Failed to process pending keyword:", error);
    }
  };

  const handleAddProduct = async (asin: string, category: string) => {
    try {
      await fetch("/api/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asin, category }),
      });
    } catch (error) {
      console.error("Failed to add product:", error);
    }
  };

  const handleAddSupplier = async (data: Record<string, string>) => {
    try {
      await fetch("/api/suppliers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
    } catch (error) {
      console.error("Failed to add supplier:", error);
    }
  };

  const handleAddCategory = async (name: string) => {
    try {
      await fetch("/api/categories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      fetchData();
    } catch (error) {
      console.error("Failed to add category:", error);
    }
  };

  const tabs = [
    { key: "keywords" as const, label: "Watchlist", count: keywords.length },
    { key: "pending" as const, label: "Pending", count: pending.length },
    { key: "import" as const, label: "Bulk Import", count: 0 },
    { key: "collectors" as const, label: "Collectors", count: 0 },
  ];

  const filteredKeywords = selectedCategory
    ? keywords.filter((k) => k.category === selectedCategory)
    : keywords;

  return (
    <main className="min-h-screen p-4 md:p-6 lg:p-8 max-w-[1200px] mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between mb-8 animate-fade-in">
        <div>
          <Link href="/" className="text-slate-500 hover:text-slate-300 text-xs transition-colors">
            &larr; Dashboard
          </Link>
          <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight mt-1">
            Admin <span className="text-emerald-400">Panel</span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage keywords, categories, and data collectors
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          {categories.length} categories | {keywords.length} keywords
        </div>
      </header>

      {/* Category Filter */}
      <div className="mb-6">
        <CategoryFilter
          categories={categories}
          colorMap={colorMap}
          selected={selectedCategory}
          onSelect={setSelectedCategory}
          onAddCategory={handleAddCategory}
        />
      </div>

      {/* Quick Add Panel */}
      <div className="glass-card p-5 mb-6">
        <h2 className="text-xs text-slate-500 uppercase tracking-wider font-medium mb-4">
          Quick Add
        </h2>
        <AdminPanel
          onAddKeyword={handleAddKeyword}
          onAddProduct={handleAddProduct}
          onAddSupplier={handleAddSupplier}
          categories={categories.map((c) => c.name)}
        />
      </div>

      {/* Tabs */}
      <div className="glass-card p-5">
        <div className="flex gap-1 mb-5 border-b border-white/5 pb-3">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 rounded-lg text-xs font-medium transition-all flex items-center gap-2 ${
                activeTab === tab.key
                  ? "bg-white/10 text-white"
                  : "text-slate-500 hover:text-slate-300 hover:bg-white/[0.03]"
              }`}
            >
              {tab.label}
              {tab.count > 0 && (
                <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${
                  activeTab === tab.key ? "bg-white/15" : "bg-white/5"
                }`}>
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-48">
            <div className="text-slate-500 animate-pulse">Loading...</div>
          </div>
        ) : (
          <>
            {activeTab === "keywords" && (
              <KeywordTable
                keywords={filteredKeywords}
                colorMap={colorMap}
                onToggle={handleToggleKeyword}
                onAdd={handleAddKeyword}
              />
            )}
            {activeTab === "pending" && (
              <PendingKeywords
                pending={pending}
                colorMap={colorMap}
                onAction={handlePendingAction}
              />
            )}
            {activeTab === "import" && (
              <BulkImport onImportComplete={fetchData} />
            )}
            {activeTab === "collectors" && (
              <CollectorStatus />
            )}
          </>
        )}
      </div>

      {/* Footer */}
      <footer className="mt-12 text-center text-xs text-slate-600 pb-6">
        NicheScope Admin v1.0
      </footer>
    </main>
  );
}
