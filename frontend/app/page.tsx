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
import HotNow from "@/components/HotNow";
import ArticleOpportunities from "@/components/ArticleOpportunities";
import NicheHunter from "@/components/NicheHunter";
import QuickAddModal from "@/components/QuickAddModal";
import KeywordSearch from "@/components/KeywordSearch";
import Skeleton from "@/components/Skeleton";
import DataFreshness from "@/components/DataFreshness";

type TabKey = "hot" | "writeAbout" | "nicheHunter" | "sparklines" | "bubbles" | "margins" | "radar" | "suppliers" | "heatmap";

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
  const [activeTab, setActiveTab] = useState<TabKey>("hot");
  const [loading, setLoading] = useState(true);
  const [regionData, setRegionData] = useState<Record<string, number>>({});
  const [selectedKeyword, setSelectedKeyword] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [totalDataPoints, setTotalDataPoints] = useState<number>(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSubcategory, setSelectedSubcategory] = useState<string | null>(null);

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

      if (healthRes && healthRes.ok) {
        const healthData = await healthRes.json();
        if (healthData.last_collection) {
          setLastUpdated(healthData.last_collection);
        }
        if (healthData.total_data_points) {
          setTotalDataPoints(healthData.total_data_points);
        }
      }

      if (!lastUpdated) {
        const allDates = (trendsData.trends || []).flatMap((t: KeywordTrend) =>
          t.history.map((h) => h.date)
        );
        if (allDates.length > 0) {
          const latest = allDates.sort().reverse()[0];
          setLastUpdated(latest);
        }
      }

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
    const interval = setInterval(fetchData, 600000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // ─── Search filter helper ───
  const sq = searchQuery.toLowerCase().trim();
  const matchesSearch = (keyword: string) =>
    !sq || keyword.toLowerCase().includes(sq);

  // ─── Build subcategory list from trends in the selected category ───
  const subcategories: string[] = [];
  if (selectedCategory) {
    const subSet = new Set<string>();
    for (const t of trends) {
      if (t.category === selectedCategory && t.subcategory) {
        subSet.add(t.subcategory);
      }
    }
    subcategories.push(...Array.from(subSet).sort());
  }

  // Wrapper: clear subcategory when category changes
  const handleSelectCategory = (cat: string | null) => {
    setSelectedCategory(cat);
    setSelectedSubcategory(null);
  };

  // ─── Filtered data (category + subcategory + search compose together) ───
  const filteredTrends = trends.filter(
    (t) =>
      (!selectedCategory || t.category === selectedCategory) &&
      (!selectedSubcategory || t.subcategory === selectedSubcategory) &&
      matchesSearch(t.keyword)
  );

  const filteredRising = risingKeywords.filter(
    (k) =>
      (!selectedCategory || k.category === selectedCategory) &&
      matchesSearch(k.keyword)
  );

  const filteredAlerts = alerts.filter((a) => {
    if (selectedCategory) {
      const data = a.data || {};
      const catMatch =
        (data as any).category === selectedCategory ||
        a.message?.toLowerCase().includes(selectedCategory);
      if (!catMatch) return false;
    }
    if (sq) {
      return a.message?.toLowerCase().includes(sq);
    }
    return true;
  });

  // ─── Derived stats (from unfiltered data for global counts) ───
  const keywordsCollected = trends.length;
  const categoriesActive = categories.length;

  const topMover = trends.length > 0
    ? [...trends].sort((a, b) => Math.abs(b.velocity_4w) - Math.abs(a.velocity_4w))[0]
    : null;

  const trendMap: Record<string, number[]> = {};
  for (const trend of trends) {
    trendMap[trend.keyword] = trend.history
      .slice()
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((h) => h.interest_score)
      .slice(-12);
  }

  const tabs: { key: TabKey; label: string }[] = [
    { key: "hot", label: "Hot Right Now" },
    { key: "writeAbout", label: "Write About" },
    { key: "nicheHunter", label: "Niche Hunter" },
    { key: "sparklines", label: "Sparkline Grid" },
    { key: "bubbles", label: "Bubble Map" },
    { key: "margins", label: "Margin Analysis" },
    { key: "radar", label: "Niche Radar" },
    { key: "suppliers", label: "Supplier Intel" },
    { key: "heatmap", label: "Geo Heatmap" },
  ];

  return (
    <main className="min-h-screen p-5 md:p-7 lg:p-10 max-w-[1600px] mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between mb-7 animate-fade-in">
        <div>
          <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-slate-100">
            Niche<span className="text-emerald-400">Scope</span>
          </h1>
          <div className="flex items-center gap-4 mt-1">
            <p className="text-sm text-slate-500">
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
          className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-500 hover:text-slate-300 bg-white/[0.02] hover:bg-white/[0.05] border border-white/5 transition-all"
        >
          Admin Panel
        </Link>
      </header>

      {/* Category Filter */}
      <div className="mb-7 animate-fade-in">
        <CategoryFilter
          categories={categories}
          colorMap={colorMap}
          selected={selectedCategory}
          onSelect={handleSelectCategory}
        />
      </div>

      {/* Subcategory chips — shown when a category is selected and subcategories exist */}
      {selectedCategory && subcategories.length > 0 && (
        <div className="mb-4 flex items-center gap-1.5 flex-wrap animate-fade-in">
          <span className="text-[10px] text-slate-600 mr-1">Sub:</span>
          <button
            onClick={() => setSelectedSubcategory(null)}
            className={`px-2.5 py-1 rounded-lg text-[10px] font-medium transition-all ${
              !selectedSubcategory
                ? "bg-white/[0.08] text-slate-200"
                : "text-slate-500 hover:text-slate-400 bg-white/[0.02]"
            }`}
          >
            All
          </button>
          {subcategories.map((sub) => {
            const count = trends.filter(
              (t) => t.category === selectedCategory && t.subcategory === sub
            ).length;
            return (
              <button
                key={sub}
                onClick={() =>
                  setSelectedSubcategory(selectedSubcategory === sub ? null : sub)
                }
                className={`px-2.5 py-1 rounded-lg text-[10px] font-medium transition-all capitalize ${
                  selectedSubcategory === sub
                    ? "bg-white/[0.08] text-slate-200"
                    : "text-slate-500 hover:text-slate-400 bg-white/[0.02]"
                }`}
              >
                {sub.replace(/_/g, " ")}
                <span className="ml-1 opacity-50">{count}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Keyword Search */}
      <div className="mb-5 max-w-md animate-fade-in">
        <KeywordSearch
          value={searchQuery}
          onChange={setSearchQuery}
          resultCount={sq ? filteredTrends.length : undefined}
        />
      </div>

      {/* Stats Bar — muted labels, restrained colors */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-7 animate-slide-up">
        <div className="glass-card p-6">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">
            Keywords Tracked
          </div>
          <div className="font-mono text-xl font-bold text-slate-200">
            {keywordsCollected}
          </div>
        </div>
        <div className="glass-card p-6">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">
            Categories Active
          </div>
          <div className="font-mono text-xl font-bold text-slate-200">
            {categoriesActive}
          </div>
        </div>
        <div className="glass-card p-6">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">
            Top Mover (4w)
          </div>
          {topMover ? (
            <div className="flex items-baseline gap-2">
              <span className="text-sm font-semibold text-slate-300 truncate max-w-[120px]">
                {topMover.keyword}
              </span>
              <span
                className="font-mono text-sm font-bold"
                style={{ color: topMover.velocity_4w >= 0 ? "#34D399" : "#FB7185" }}
              >
                {topMover.velocity_4w >= 0 ? "+" : ""}{topMover.velocity_4w}%
              </span>
            </div>
          ) : (
            <div className="text-slate-600 text-sm">&mdash;</div>
          )}
        </div>
        <div className="glass-card p-6">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">
            Data Points
          </div>
          <div className="font-mono text-xl font-bold text-slate-200">
            {totalDataPoints > 0
              ? totalDataPoints.toLocaleString()
              : trends.reduce((sum, t) => sum + t.history.length, 0).toLocaleString()}
          </div>
        </div>
      </div>

      {/* Main Layout: Sidebar + Content */}
      <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr_320px] gap-6">
        {/* Left Sidebar: Niche Rankings */}
        <div className="space-y-3">
          <h2 className="text-[10px] text-slate-500 uppercase tracking-wider font-medium px-1">
            Niche Rankings
          </h2>
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="glass-card p-5 animate-pulse h-32" />
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
                    handleSelectCategory(
                      selectedCategory === score.category ? null : score.category
                    )
                  }
                />
              ))
          ) : (
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
            <h2 className="text-[10px] text-slate-500 uppercase tracking-wider font-medium mb-4">
              Trend Overview
              <span className="text-slate-600 ml-2 normal-case text-[10px]">
                Interest over time
              </span>
            </h2>
            {loading ? (
              <div className="flex items-center justify-center h-full">
                <Skeleton type="chart" />
              </div>
            ) : (
              <TrendChart
                trends={filteredTrends}
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
              <div className="glass-card p-6 animate-slide-up">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <span
                      className="w-2.5 h-2.5 rounded-full"
                      style={{ backgroundColor: color }}
                    />
                    <h3 className="font-display font-semibold text-lg text-slate-200">
                      {kwData.keyword}
                    </h3>
                    <span className="text-[10px] text-slate-500 uppercase tracking-wider px-2 py-0.5 rounded-full bg-white/[0.04]">
                      {kwData.category}
                    </span>
                  </div>
                  <button
                    onClick={() => setSelectedKeyword(null)}
                    className="text-slate-500 hover:text-slate-300 transition-colors text-lg leading-none"
                    aria-label="Close keyword detail"
                  >
                    &times;
                  </button>
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <div className="glass-card p-4">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Current Interest</div>
                    <div className="font-mono text-xl font-bold text-slate-200">{kwData.current_interest}</div>
                  </div>
                  <div className="glass-card p-4">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">4-Week Velocity</div>
                    <div className="font-mono text-xl font-bold" style={{ color: kwData.velocity_4w >= 0 ? "#34D399" : "#FB7185" }}>
                      {kwData.velocity_4w >= 0 ? "+" : ""}{kwData.velocity_4w}%
                    </div>
                  </div>
                  <div className="glass-card p-4">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">12-Week Velocity</div>
                    <div className="font-mono text-xl font-bold" style={{ color: kwData.velocity_12w >= 0 ? "#34D399" : "#FB7185" }}>
                      {kwData.velocity_12w >= 0 ? "+" : ""}{kwData.velocity_12w}%
                    </div>
                  </div>
                </div>
                {kwData.related_rising && kwData.related_rising.length > 0 && (
                  <div className="mt-4">
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Related Rising Keywords</div>
                    <div className="flex flex-wrap gap-2">
                      {kwData.related_rising.map((rk: string) => (
                        <span key={rk} className="text-xs px-2 py-1 rounded-full bg-white/[0.04] text-slate-400">
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
            <div className="flex gap-1 mb-4 border-b border-white/[0.04] pb-3 overflow-x-auto" role="tablist">
              {tabs.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  role="tab"
                  aria-selected={activeTab === tab.key}
                  tabIndex={0}
                  className={`px-4 py-2 rounded-lg text-xs font-medium transition-all whitespace-nowrap shrink-0 ${
                    activeTab === tab.key
                      ? "bg-white/[0.08] text-slate-200"
                      : "text-slate-500 hover:text-slate-400 hover:bg-white/[0.02]"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="h-[380px]" role="tabpanel">
              {loading ? (
                <Skeleton type={
                  activeTab === "hot" ? "list" :
                  activeTab === "writeAbout" ? "list" :
                  activeTab === "nicheHunter" ? "list" :
                  activeTab === "sparklines" ? "chart" :
                  activeTab === "bubbles" ? "chart" :
                  activeTab === "margins" ? "chart" :
                  activeTab === "radar" ? "radar" :
                  activeTab === "suppliers" ? "table" :
                  "map"
                } />
              ) : (
                <>
                  {activeTab === "hot" && (
                    <HotNow
                      trends={filteredTrends}
                      colorMap={colorMap}
                      onKeywordClick={(kw) =>
                        setSelectedKeyword(selectedKeyword === kw ? null : kw)
                      }
                    />
                  )}
                  {activeTab === "writeAbout" && (
                    <ArticleOpportunities
                      trends={filteredTrends}
                      colorMap={colorMap}
                    />
                  )}
                  {activeTab === "nicheHunter" && (
                    <NicheHunter colorMap={colorMap} />
                  )}
                  {activeTab === "sparklines" && (
                    <SparklineGrid
                      trends={filteredTrends}
                      colorMap={colorMap}
                    />
                  )}
                  {activeTab === "bubbles" && (
                    <BubbleChart
                      keywords={filteredTrends}
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

        {/* Right Sidebar */}
        <div className="space-y-6">
          <div className="glass-card p-5">
            <h2 className="text-[10px] text-slate-500 uppercase tracking-wider font-medium mb-3 px-1">
              Rising Keywords
            </h2>
            {loading ? (
              <Skeleton type="list" />
            ) : (
              <div className="max-h-[350px] overflow-y-auto">
                <RisingKeywords
                  keywords={filteredRising}
                  colorMap={colorMap}
                  trendMap={trendMap}
                />
              </div>
            )}
          </div>

          <div className="glass-card p-5">
            <h2 className="text-[10px] text-slate-500 uppercase tracking-wider font-medium mb-3 px-1">
              Breakout Signals
            </h2>
            {loading ? (
              <Skeleton type="list" />
            ) : (
              <div className="max-h-[350px] overflow-y-auto">
                <BreakoutSignals alerts={filteredAlerts} />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Floating Quick Add Button */}
      <button
        onClick={() => setQuickAddOpen(true)}
        className="fixed bottom-6 right-6 w-12 h-12 rounded-full bg-emerald-500/80 hover:bg-emerald-500 text-white text-2xl shadow-lg shadow-emerald-500/15 transition-all hover:scale-105 z-30 flex items-center justify-center"
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
        NicheScope v1.0 · Data refreshes every 10 minutes
        {lastUpdated && (
          <span className="text-slate-700">
            {" "}· Last collection: {new Date(lastUpdated).toLocaleString()}
          </span>
        )}
      </footer>
    </main>
  );
}
