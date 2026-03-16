"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import type {
  KeywordTrend,
  NicheScore,
  Supplier,
  Alert,
  StatsOverview,
} from "@/lib/types";
import { getCategoryColorMap, type CategoryInfo } from "@/lib/colors";
import { formatPercent } from "@/lib/utils";

import CategoryFilter from "@/components/CategoryFilter";
import WordCloud from "@/components/WordCloud";
import NicheCard from "@/components/NicheCard";
import TrendChart from "@/components/TrendChart";
import MarginAnalysis from "@/components/MarginAnalysis";
import NicheRadar from "@/components/NicheRadar";
import SupplierTable from "@/components/SupplierTable";
import RisingKeywords from "@/components/RisingKeywords";
import BreakoutSignals from "@/components/BreakoutSignals";
import HeatMap from "@/components/HeatMap";
import QuickAddModal from "@/components/QuickAddModal";
import Skeleton from "@/components/Skeleton";

type TabKey = "trends" | "margins" | "radar" | "suppliers" | "heatmap";

export default function Dashboard() {
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [colorMap, setColorMap] = useState<Record<string, string>>({});
  const [quickAddOpen, setQuickAddOpen] = useState(false);
  const [trends, setTrends] = useState<KeywordTrend[]>([]);
  const [scores, setScores] = useState<NicheScore[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [risingKeywords, setRisingKeywords] = useState<
    { keyword: string; category: string; interest_score: number; change_pct: number }[]
  >([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("trends");
  const [loading, setLoading] = useState(true);
  const [regionData, setRegionData] = useState<Record<string, number>>({});
  const [selectedKeyword, setSelectedKeyword] = useState<string | null>(null);

  const handleQuickAdd = async (keyword: string, category: string) => {
    await fetch("/api/keywords", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword, category }),
    });
    fetchData();
  };

  const fetchData = useCallback(async () => {
    try {
      const [catRes, trendsRes, keywordsRes, suppliersRes] = await Promise.all([
        fetch("/api/categories"),
        fetch(`/api/trends?days=90${selectedCategory ? `&category=${selectedCategory}` : ""}`),
        fetch("/api/keywords?rising=true&limit=20"),
        fetch("/api/suppliers"),
      ]);

      const catData = await catRes.json();
      const trendsData = await trendsRes.json();
      const keywordsData = await keywordsRes.json();
      const suppliersData = await suppliersRes.json();

      const cats = catData.categories || [];
      setCategories(cats);
      setColorMap(getCategoryColorMap(cats));

      setTrends(trendsData.trends || []);
      setScores(trendsData.scores || []);
      setRisingKeywords(keywordsData.keywords || []);
      setAlerts(keywordsData.alerts || []);
      setSuppliers(suppliersData.suppliers || []);

      // Extract region data from first trend with region data
      const trendWithRegion = (trendsData.trends || []).find(
        (t: KeywordTrend) => t.region_data && Object.keys(t.region_data).length > 0
      );
      if (trendWithRegion) {
        setRegionData(trendWithRegion.region_data);
      }
    } catch (error) {
      console.error("Failed to fetch data:", error);
    } finally {
      setLoading(false);
    }
  }, [selectedCategory]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 600000); // 10 minutes
    return () => clearInterval(interval);
  }, [fetchData]);

  // Calculate stats
  const stats: StatsOverview = {
    niches_tracked: categories.length || scores.length || 0,
    avg_growth:
      trends.length > 0
        ? trends.reduce((sum, t) => sum + t.velocity_4w, 0) / trends.length
        : 0,
    best_margin: scores.length > 0 ? Math.max(...scores.map((s) => s.margin_score)) : 0,
    top_signal:
      alerts.length > 0 ? alerts[0]?.message?.slice(0, 40) || "No signals" : "No signals yet",
  };

  const tabs: { key: TabKey; label: string }[] = [
    { key: "trends", label: "Trend Lines" },
    { key: "margins", label: "Margin Analysis" },
    { key: "radar", label: "Niche Radar" },
    { key: "suppliers", label: "Supplier Intel" },
    { key: "heatmap", label: "Geo Heatmap" },
  ];

  return (
    <main className="min-h-screen p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between mb-6 animate-fade-in">
        <div>
          <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight">
            Niche<span className="text-emerald-400">Scope</span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            E-Commerce Niche Research Dashboard
          </p>
        </div>
        <Link
          href="/admin"
          className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-500 hover:text-white bg-white/[0.03] hover:bg-white/[0.06] border border-white/5 transition-all"
        >
          Admin Panel
        </Link>
      </header>

      {/* Category Filter */}
      <div className="mb-6 animate-fade-in">
        <CategoryFilter
          categories={categories}
          colorMap={colorMap}
          selected={selectedCategory}
          onSelect={setSelectedCategory}
        />
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6 animate-slide-up">
        {[
          {
            label: "Niches Tracked",
            value: stats.niches_tracked.toString(),
            color: "#60A5FA",
          },
          {
            label: "Avg Growth Rate",
            value: formatPercent(stats.avg_growth),
            color: stats.avg_growth >= 0 ? "#34D399" : "#EF4444",
          },
          {
            label: "Best Margin Score",
            value: stats.best_margin.toFixed(0),
            color: "#FBBF24",
          },
          {
            label: "Top Signal",
            value: stats.top_signal,
            color: "#A78BFA",
            isText: true,
          },
        ].map((stat, i) => (
          <div key={i} className="glass-card p-4">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
              {stat.label}
            </div>
            <div
              className={`${
                (stat as any).isText ? "text-sm truncate" : "font-mono text-xl"
              } font-bold`}
              style={{ color: stat.color }}
            >
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      {/* Main Layout: Sidebar + Content */}
      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr_300px] gap-6">
        {/* Left Sidebar: Niche Rankings */}
        <div className="space-y-3">
          <h2 className="text-xs text-slate-500 uppercase tracking-wider font-medium px-1">
            Niche Rankings
          </h2>
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="glass-card p-4 animate-pulse h-28" />
              ))}
            </div>
          ) : scores.length > 0 ? (
            scores
              .sort((a, b) => b.overall_score - a.overall_score)
              .map((score, i) => (
                <NicheCard
                  key={score.category}
                  rank={i + 1}
                  score={score}
                  colorMap={colorMap}
                  trendHistory={
                    trends
                      .find((t) => t.category === score.category)
                      ?.history.slice(0, 12)
                      .map((h) => h.interest_score)
                      .reverse() || []
                  }
                  isSelected={selectedCategory === score.category}
                  onClick={() =>
                    setSelectedCategory(
                      selectedCategory === score.category ? null : score.category
                    )
                  }
                />
              ))
          ) : (
            // Demo cards when no data
            categories.slice(0, 6).map((cat, i) => (
              <NicheCard
                key={cat.name}
                rank={i + 1}
                colorMap={colorMap}
                score={{
                  category: cat.name,
                  date: new Date().toISOString(),
                  trend_score: 65 + Math.random() * 20,
                  margin_score: 60 + Math.random() * 25,
                  competition_score: 50 + Math.random() * 30,
                  sourcing_score: 70 + Math.random() * 15,
                  content_score: 55 + Math.random() * 25,
                  repeat_purchase_score: 40 + Math.random() * 40,
                  overall_score: 60 + Math.random() * 20,
                }}
                trendHistory={Array.from({ length: 12 }, () => 30 + Math.random() * 50)}
                isSelected={selectedCategory === cat.name}
                onClick={() =>
                  setSelectedCategory(
                    selectedCategory === cat.name ? null : cat.name
                  )
                }
              />
            ))
          )}
        </div>

        {/* Center: Main Content Area */}
        <div className="space-y-6">
          {/* Word Cloud Hero */}
          <div className="glass-card p-6 h-[420px]">
            <h2 className="text-xs text-slate-500 uppercase tracking-wider font-medium mb-4">
              Keyword Universe
              <span className="text-slate-600 ml-2 normal-case">
                Size = growth velocity
              </span>
            </h2>
            {loading ? (
              <div className="flex items-center justify-center h-full">
                <Skeleton type="chart" />
              </div>
            ) : (
              <WordCloud
                keywords={
                  selectedCategory
                    ? trends.filter((t) => t.category === selectedCategory)
                    : trends
                }
                colorMap={colorMap}
                selectedKeyword={selectedKeyword}
                onKeywordClick={(kw) => {
                  setSelectedKeyword(selectedKeyword === kw ? null : kw);
                }}
              />
            )}
          </div>

          {/* Keyword Detail Panel */}
          {selectedKeyword && (() => {
            const kwData = trends.find(t => t.keyword === selectedKeyword);
            if (!kwData) return null;
            const color = colorMap[kwData.category] || "#94a3b8";
            return (
              <div className="glass-card p-5 animate-slide-up">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <span
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: color }}
                    />
                    <h3 className="font-display font-semibold text-lg" style={{ color }}>
                      {kwData.keyword}
                    </h3>
                    <span className="text-xs text-slate-500 uppercase tracking-wider px-2 py-0.5 rounded-full bg-white/5">
                      {kwData.category}
                    </span>
                  </div>
                  <button
                    onClick={() => setSelectedKeyword(null)}
                    className="text-slate-500 hover:text-white transition-colors text-lg leading-none"
                    aria-label="Close keyword detail"
                  >
                    &times;
                  </button>
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <div className="glass-card p-3">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Current Interest</div>
                    <div className="font-mono text-xl font-bold" style={{ color }}>{kwData.current_interest}</div>
                  </div>
                  <div className="glass-card p-3">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">4-Week Velocity</div>
                    <div className="font-mono text-xl font-bold" style={{ color: kwData.velocity_4w >= 0 ? "#34D399" : "#EF4444" }}>
                      {kwData.velocity_4w >= 0 ? "+" : ""}{kwData.velocity_4w}%
                    </div>
                  </div>
                  <div className="glass-card p-3">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">12-Week Velocity</div>
                    <div className="font-mono text-xl font-bold" style={{ color: kwData.velocity_12w >= 0 ? "#34D399" : "#EF4444" }}>
                      {kwData.velocity_12w >= 0 ? "+" : ""}{kwData.velocity_12w}%
                    </div>
                  </div>
                </div>
                {kwData.related_rising && kwData.related_rising.length > 0 && (
                  <div className="mt-4">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Related Rising Keywords</div>
                    <div className="flex flex-wrap gap-2">
                      {kwData.related_rising.map((rk: string) => (
                        <span key={rk} className="text-xs px-2 py-1 rounded-full bg-white/5 text-slate-300">
                          {rk}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })()}

          {/* Tab Panel */}
          <div className="glass-card p-6">
            <div className="flex gap-1 mb-4 border-b border-white/5 pb-3" role="tablist">
              {tabs.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  role="tab"
                  aria-selected={activeTab === tab.key}
                  tabIndex={0}
                  className={`px-4 py-2 rounded-lg text-xs font-medium transition-all ${
                    activeTab === tab.key
                      ? "bg-white/10 text-white"
                      : "text-slate-500 hover:text-slate-300 hover:bg-white/[0.03]"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="h-[350px]" role="tabpanel">
              {loading ? (
                <Skeleton type={
                  activeTab === "trends" ? "chart" :
                  activeTab === "margins" ? "chart" :
                  activeTab === "radar" ? "radar" :
                  activeTab === "suppliers" ? "table" :
                  "map"
                } />
              ) : (
                <>
                  {activeTab === "trends" && (
                    <TrendChart trends={trends} selectedCategory={selectedCategory} colorMap={colorMap} />
                  )}
                  {activeTab === "margins" && (
                    <MarginAnalysis suppliers={suppliers} selectedCategory={selectedCategory} />
                  )}
                  {activeTab === "radar" && (
                    <NicheRadar
                      scores={selectedCategory ? scores.filter(s => s.category === selectedCategory) : scores}
                      colorMap={colorMap}
                    />
                  )}
                  {activeTab === "suppliers" && (
                    <SupplierTable
                      suppliers={selectedCategory ? suppliers.filter(s => s.product_focus.toLowerCase().includes(selectedCategory)) : suppliers}
                    />
                  )}
                  {activeTab === "heatmap" && (
                    <HeatMap
                      regionData={regionData}
                      category={selectedCategory || categories[0]?.name || "beauty"}
                      colorMap={colorMap}
                    />
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        {/* Right Sidebar: Rising Keywords + Breakout Signals */}
        <div className="space-y-6">
          <div className="glass-card p-4">
            <h2 className="text-xs text-slate-500 uppercase tracking-wider font-medium mb-3 px-1">
              Rising Keywords
            </h2>
            {loading ? (
              <Skeleton type="list" />
            ) : (
              <div className="max-h-[300px] overflow-y-auto">
                <RisingKeywords
                  keywords={
                    selectedCategory
                      ? risingKeywords.filter((k) => k.category === selectedCategory)
                      : risingKeywords
                  }
                  colorMap={colorMap}
                />
              </div>
            )}
          </div>

          <div className="glass-card p-4">
            <h2 className="text-xs text-slate-500 uppercase tracking-wider font-medium mb-3 px-1">
              Breakout Signals
            </h2>
            {loading ? (
              <Skeleton type="list" />
            ) : (
              <div className="max-h-[350px] overflow-y-auto">
                <BreakoutSignals alerts={selectedCategory ? alerts.filter(a => {
                  const data = a.data || {};
                  return (data as any).category === selectedCategory || a.message?.toLowerCase().includes(selectedCategory);
                }) : alerts} />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Floating Quick Add Button */}
      <button
        onClick={() => setQuickAddOpen(true)}
        className="fixed bottom-6 right-6 w-12 h-12 rounded-full bg-emerald-500 hover:bg-emerald-400 text-white text-2xl shadow-lg shadow-emerald-500/25 transition-all hover:scale-110 z-30 flex items-center justify-center"
        title="Quick add keyword"
        aria-label="Add new keyword"
      >
        +
      </button>

      {/* Quick Add Modal */}
      <QuickAddModal
        open={quickAddOpen}
        onClose={() => setQuickAddOpen(false)}
        onAdd={handleQuickAdd}
        categories={categories.map((c) => c.name)}
      />

      {/* Footer */}
      <footer className="mt-12 text-center text-xs text-slate-600 pb-6">
        NicheScope v1.0 &middot; Data refreshes automatically
      </footer>
    </main>
  );
}
