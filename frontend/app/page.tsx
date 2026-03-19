"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import type {
  KeywordTrend,
  NicheScore,
  Supplier,
  Alert,
} from "@/lib/types";
import { getCategoryColorMap, type CategoryInfo } from "@/lib/colors";

import CategoryFilter from "@/components/CategoryFilter";
import BubbleChart from "@/components/BubbleChart";
import SparklineGrid from "@/components/SparklineGrid";
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
import DataFreshness from "@/components/DataFreshness";

type TabKey = "sparklines" | "bubbles" | "margins" | "radar" | "suppliers" | "heatmap";

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
  const [activeTab, setActiveTab] = useState<TabKey>("sparklines");
  const [loading, setLoading] = useState(true);
  const [regionData, setRegionData] = useState<Record<string, number>>({});
  const [selectedKeyword, setSelectedKeyword] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [totalDataPoints, setTotalDataPoints] = useState<number>(0);

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
      const [catRes, trendsRes, keywordsRes, suppliersRes, healthRes] = await Promise.all([
        fetch("/api/categories"),
        fetch(`/api/trends?days=90${selectedCategory ? `&category=${selectedCategory}` : ""}`),
        fetch("/api/keywords?rising=true&limit=20"),
        fetch("/api/suppliers"),
        fetch("/api/health").catch(() => null),
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

      // Extract last updated from health or trends
      if (healthRes && healthRes.ok) {
        const healthData = await healthRes.json();
        if (healthData.last_collection) {
          setLastUpdated(healthData.last_collection);
        }
        if (healthData.total_data_points) {
          setTotalDataPoints(healthData.total_data_points);
        }
      }

      // Fallback: derive last updated from most recent trend history date
      if (!lastUpdated) {
        const allDates = (trendsData.trends || []).flatMap((t: KeywordTrend) =>
          t.history.map((h) => h.date)
        );
        if (allDates.length > 0) {
          const latest = allDates.sort().reverse()[0];
          setLastUpdated(latest);
        }
      }

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

  // ─── Actionable Stats ───
  const keywordsCollected = trends.length;
  const categoriesActive = categories.length;

  // Find the top mover: keyword with highest absolute 4w velocity
  const topMover = trends.length > 0
    ? [...trends].sort((a, b) => Math.abs(b.velocity_4w) - Math.abs(a.velocity_4w))[0]
    : null;

  // Build trend sparkline map for rising keywords sidebar
  const trendMap: Record<string, number[]> = {};
  for (const trend of trends) {
    trendMap[trend.keyword] = trend.history
      .slice()
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((h) => h.interest_score)
      .slice(-12);
  }

  const tabs: { key: TabKey; label: string }[] = [
    { key: "sparklines", label: "Sparkline Grid" },
    { key: "bubbles", label: "Bubble Map" },
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
          <div className="flex items-center gap-4 mt-1">
            <p className="text-sm text-slate-400">
              E-Commerce Niche Research Dashboard
            </p>
            <DataFreshness
              lastUpdated={lastUpdated}
              totalDataPoints={totalDataPoints}
            />
          </div>
        </div>
        <Link
          href="/admin"
          className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white bg-white/[0.03] hover:bg-white/[0.06] border border-white/5 transition-all"
        >
          Admin Panel
        </Link>
      </header>

      {/* Category Filter — horizontal scroll */}
      <div className="mb-6 animate-fade-in">
        <CategoryFilter
          categories={categories}
          colorMap={colorMap}
          selected={selectedCategory}
          onSelect={setSelectedCategory}
        />
      </div>

      {/* Stats Bar — actionable metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6 animate-slide-up">
        <div className="glass-card p-4">
          <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">
            Keywords Tracked
          </div>
          <div className="font-mono text-xl font-bold text-blue-400">
            {keywordsCollected}
          </div>
        </div>
        <div className="glass-card p-4">
          <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">
            Categories Active
          </div>
          <div className="font-mono text-xl font-bold text-purple-400">
            {categoriesActive}
          </div>
        </div>
        <div className="glass-card p-4">
          <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">
            Top Mover (4w)
          </div>
          {topMover ? (
            <div className="flex items-baseline gap-2">
              <span
                className="text-sm font-semibold truncate max-w-[120px]"
                style={{ color: colorMap[topMover.category] || "#94a3b8" }}
              >
                {topMover.keyword}
              </span>
              <span
                className="font-mono text-sm font-bold"
                style={{ color: topMover.velocity_4w >= 0 ? "#34D399" : "#EF4444" }}
              >
                {topMover.velocity_4w >= 0 ? "+" : ""}{topMover.velocity_4w}%
              </span>
            </div>
          ) : (
            <div className="text-slate-500 text-sm">—</div>
          )}
        </div>
        <div className="glass-card p-4">
          <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">
            Data Points
          </div>
          <div className="font-mono text-xl font-bold text-emerald-400">
            {totalDataPoints > 0 ? totalDataPoints.toLocaleString() : trends.reduce((sum, t) => sum + t.history.length, 0).toLocaleString()}
          </div>
        </div>
      </div>

      {/* Main Layout: Sidebar + Content */}
      <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr_320px] gap-6">
        {/* Left Sidebar: Niche Rankings */}
        <div className="space-y-3">
          <h2 className="text-xs text-slate-400 uppercase tracking-wider font-medium px-1">
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
            /* Empty state — no fake data */
            <div className="glass-card p-6 text-center">
              <div className="text-slate-500 text-sm mb-2">No niche scores yet</div>
              <div className="text-slate-600 text-xs">
                Scores are calculated after collecting enough trend data across categories.
              </div>
            </div>
          )}
        </div>

        {/* Center: Main Content Area */}
        <div className="space-y-6">
          {/* HERO: Trend Chart */}
          <div className="glass-card p-6 h-[420px]">
            <h2 className="text-xs text-slate-400 uppercase tracking-wider font-medium mb-4">
              Trend Overview
              <span className="text-slate-500 ml-2 normal-case">
                Interest over time — top keywords
              </span>
            </h2>
            {loading ? (
              <div className="flex items-center justify-center h-full">
                <Skeleton type="chart" />
              </div>
            ) : (
              <TrendChart
                trends={trends}
                selectedCategory={selectedCategory}
                colorMap={colorMap}
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
                    <span className="text-xs text-slate-400 uppercase tracking-wider px-2 py-0.5 rounded-full bg-white/5">
                      {kwData.category}
                    </span>
                  </div>
                  <button
                    onClick={() => setSelectedKeyword(null)}
                    className="text-slate-400 hover:text-white transition-colors text-lg leading-none"
                    aria-label="Close keyword detail"
                  >
                    &times;
                  </button>
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <div className="glass-card p-3">
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Current Interest</div>
                    <div className="font-mono text-xl font-bold" style={{ color }}>{kwData.current_interest}</div>
                  </div>
                  <div className="glass-card p-3">
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">4-Week Velocity</div>
                    <div className="font-mono text-xl font-bold" style={{ color: kwData.velocity_4w >= 0 ? "#34D399" : "#EF4444" }}>
                      {kwData.velocity_4w >= 0 ? "+" : ""}{kwData.velocity_4w}%
                    </div>
                  </div>
                  <div className="glass-card p-3">
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">12-Week Velocity</div>
                    <div className="font-mono text-xl font-bold" style={{ color: kwData.velocity_12w >= 0 ? "#34D399" : "#EF4444" }}>
                      {kwData.velocity_12w >= 0 ? "+" : ""}{kwData.velocity_12w}%
                    </div>
                  </div>
                </div>
                {kwData.related_rising && kwData.related_rising.length > 0 && (
                  <div className="mt-4">
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-2">Related Rising Keywords</div>
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
            <div className="flex gap-1 mb-4 border-b border-white/5 pb-3 overflow-x-auto" role="tablist">
              {tabs.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  role="tab"
                  aria-selected={activeTab === tab.key}
                  tabIndex={0}
                  className={`px-4 py-2 rounded-lg text-xs font-medium transition-all whitespace-nowrap shrink-0 ${
                    activeTab === tab.key
                      ? "bg-white/10 text-white"
                      : "text-slate-400 hover:text-slate-300 hover:bg-white/[0.03]"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="h-[380px]" role="tabpanel">
              {loading ? (
                <Skeleton type={
                  activeTab === "sparklines" ? "chart" :
                  activeTab === "bubbles" ? "chart" :
                  activeTab === "margins" ? "chart" :
                  activeTab === "radar" ? "radar" :
                  activeTab === "suppliers" ? "table" :
                  "map"
                } />
              ) : (
                <>
                  {activeTab === "sparklines" && (
                    <SparklineGrid
                      trends={trends}
                      selectedCategory={selectedCategory}
                      colorMap={colorMap}
                    />
                  )}
                  {activeTab === "bubbles" && (
                    <BubbleChart
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

        {/* Right Sidebar: Rising Keywords + Breakout Signals — wider (320px) */}
        <div className="space-y-6">
          <div className="glass-card p-4">
            <h2 className="text-xs text-slate-400 uppercase tracking-wider font-medium mb-3 px-1">
              Rising Keywords
            </h2>
            {loading ? (
              <Skeleton type="list" />
            ) : (
              <div className="max-h-[350px] overflow-y-auto">
                <RisingKeywords
                  keywords={
                    selectedCategory
                      ? risingKeywords.filter((k) => k.category === selectedCategory)
                      : risingKeywords
                  }
                  colorMap={colorMap}
                  trendMap={trendMap}
                />
              </div>
            )}
          </div>

          <div className="glass-card p-4">
            <h2 className="text-xs text-slate-400 uppercase tracking-wider font-medium mb-3 px-1">
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
      <footer className="mt-12 text-center text-xs text-slate-500 pb-6">
        NicheScope v1.0 · Data refreshes every 10 minutes
        {lastUpdated && (
          <span className="text-slate-600">
            {" "}· Last collection: {new Date(lastUpdated).toLocaleString()}
          </span>
        )}
      </footer>
    </main>
  );
}
