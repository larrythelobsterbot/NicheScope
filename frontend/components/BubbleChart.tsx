"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import * as d3 from "d3";
import { KeywordTrend } from "@/lib/types";

interface BubbleChartProps {
  keywords: KeywordTrend[];
  onKeywordClick?: (keyword: string) => void;
  colorMap?: Record<string, string>;
  selectedKeyword?: string | null;
}

/**
 * Packed Bubble Chart — circle-pack layout.
 * Size  = current_interest (volume proxy)
 * Color = velocity_4w mapped to intensity (muted → vivid)
 */
export default function BubbleChart({
  keywords,
  onKeywordClick,
  colorMap = {},
  selectedKeyword,
}: BubbleChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 380 });
  const [hoveredBubble, setHoveredBubble] = useState<string | null>(null);

  // Resize observer
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) {
        setDimensions({ width, height: Math.min(height, 420) });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Top-30 sorted by interest descending
  const topKeywords = useMemo(
    () =>
      [...keywords]
        .sort((a, b) => b.current_interest - a.current_interest)
        .slice(0, 30),
    [keywords]
  );

  useEffect(() => {
    if (!svgRef.current || topKeywords.length === 0) return;

    const { width, height } = dimensions;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    // ── Hierarchy for circle packing ──
    const root = d3
      .hierarchy({ children: topKeywords } as any)
      .sum((d: any) => Math.max(d.current_interest ?? 0, 4))
      .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));

    const pack = d3
      .pack()
      .size([width, height])
      .padding(3);

    pack(root);

    // ── Velocity → opacity scale (higher velocity = more vivid) ──
    const maxVel = Math.max(
      ...topKeywords.map((k) => Math.abs(k.velocity_4w)),
      1
    );
    const opacityScale = d3
      .scaleLinear()
      .domain([0, maxVel])
      .range([0.25, 0.85])
      .clamp(true);

    const g = svg.append("g");

    const leaves = root.leaves();

    // ── Bubble groups ──
    const bubbles = g
      .selectAll("g.bubble")
      .data(leaves)
      .join("g")
      .attr("class", "bubble")
      .attr("transform", (d: any) => `translate(${d.x},${d.y})`)
      .style("cursor", "pointer")
      .on("mouseenter", function (_, d: any) {
        setHoveredBubble(d.data.keyword);
        d3.select(this)
          .select("circle")
          .transition()
          .duration(180)
          .attr("r", (d as any).r * 1.06)
          .attr("stroke-opacity", 0.6);
      })
      .on("mouseleave", function (_, d: any) {
        setHoveredBubble(null);
        d3.select(this)
          .select("circle")
          .transition()
          .duration(180)
          .attr("r", (d as any).r)
          .attr("stroke-opacity", 0.3);
      })
      .on("click", (_, d: any) => {
        onKeywordClick?.(d.data.keyword);
      });

    // ── Circles ──
    bubbles
      .append("circle")
      .attr("r", 0)
      .attr("fill", (d: any) => {
        const color = colorMap[d.data.category] || "#94a3b8";
        const vel = Math.abs(d.data.velocity_4w ?? 0);
        const alpha = Math.round(opacityScale(vel) * 255)
          .toString(16)
          .padStart(2, "0");
        return `${color}${alpha}`;
      })
      .attr("stroke", (d: any) => colorMap[d.data.category] || "#94a3b8")
      .attr("stroke-width", 1)
      .attr("stroke-opacity", 0.3)
      .attr("opacity", (d: any) => {
        if (selectedKeyword && d.data.keyword !== selectedKeyword) return 0.12;
        return 1;
      })
      .transition()
      .duration(500)
      .delay((_, i) => i * 12)
      .attr("r", (d: any) => d.r);

    // ── Labels (only if bubble can fit text) ──
    bubbles
      .filter((d: any) => d.r > 22)
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "central")
      .attr("font-family", "Outfit, sans-serif")
      .attr("font-weight", "500")
      .attr("fill", "#e2e8f0")
      .attr("opacity", 0)
      .each(function (d: any) {
        const el = d3.select(this);
        const maxWidth = d.r * 1.6;
        const fontSize = Math.max(9, Math.min(13, d.r / 3.5));
        el.attr("font-size", `${fontSize}px`);

        // Truncate to fit within bubble
        const maxChars = Math.floor(maxWidth / (fontSize * 0.52));
        const label =
          d.data.keyword.length > maxChars
            ? d.data.keyword.slice(0, maxChars - 1) + "\u2026"
            : d.data.keyword;
        el.text(label);

        // If bubble is large enough, shift label up to make room for score
        if (d.r > 32) {
          el.attr("dy", "-0.35em");
        }
      })
      .transition()
      .duration(500)
      .delay((_, i) => i * 12 + 200)
      .attr("opacity", (d: any) => {
        if (selectedKeyword && d.data.keyword !== selectedKeyword) return 0.12;
        return 0.95;
      });

    // ── Interest score beneath label for larger bubbles ──
    bubbles
      .filter((d: any) => d.r > 32)
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "central")
      .attr("dy", "0.85em")
      .attr("font-family", "JetBrains Mono, monospace")
      .attr("font-size", "9px")
      .attr("font-weight", "600")
      .attr("fill", (d: any) => colorMap[d.data.category] || "#94a3b8")
      .attr("opacity", 0)
      .text((d: any) => d.data.current_interest)
      .transition()
      .duration(500)
      .delay((_, i) => i * 12 + 300)
      .attr("opacity", (d: any) => {
        if (selectedKeyword && d.data.keyword !== selectedKeyword) return 0.08;
        return 0.45;
      });
  }, [topKeywords, dimensions, onKeywordClick, colorMap, selectedKeyword]);

  // Tooltip data
  const hoveredData = hoveredBubble
    ? keywords.find((k) => k.keyword === hoveredBubble)
    : null;

  return (
    <div ref={containerRef} className="relative w-full h-full">
      <svg
        ref={svgRef}
        width={dimensions.width}
        height={dimensions.height}
        className="w-full h-full"
        role="img"
        aria-label="Keyword packed bubble chart"
      />

      {hoveredData && (
        <div className="absolute top-4 right-4 glass-card p-4 min-w-[190px] pointer-events-none animate-fade-in z-10">
          <div
            className="font-display font-semibold text-sm mb-1"
            style={{ color: colorMap[hoveredData.category] || "#94a3b8" }}
          >
            {hoveredData.keyword}
          </div>
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2.5">
            {hoveredData.category}
          </div>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-500">Interest</span>
              <span className="font-mono text-slate-200">
                {hoveredData.current_interest}/100
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">4w velocity</span>
              <span
                className="font-mono"
                style={{
                  color: hoveredData.velocity_4w >= 0 ? "#34D399" : "#F87171",
                }}
              >
                {hoveredData.velocity_4w >= 0 ? "+" : ""}
                {hoveredData.velocity_4w}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">12w velocity</span>
              <span
                className="font-mono"
                style={{
                  color:
                    hoveredData.velocity_12w >= 0 ? "#34D399" : "#F87171",
                }}
              >
                {hoveredData.velocity_12w >= 0 ? "+" : ""}
                {hoveredData.velocity_12w}%
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
