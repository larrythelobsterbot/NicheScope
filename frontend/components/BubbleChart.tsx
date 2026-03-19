"use client";

import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import { KeywordTrend } from "@/lib/types";

interface BubbleChartProps {
  keywords: KeywordTrend[];
  onKeywordClick?: (keyword: string) => void;
  colorMap?: Record<string, string>;
  selectedKeyword?: string | null;
}

interface BubbleNode extends d3.SimulationNodeDatum {
  keyword: string;
  category: string;
  interest: number;
  velocity4w: number;
  velocity12w: number;
  radius: number;
  related_rising: string[];
}

export default function BubbleChart({
  keywords,
  onKeywordClick,
  colorMap = {},
  selectedKeyword,
}: BubbleChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 380 });
  const [hoveredBubble, setHoveredBubble] = useState<string | null>(null);

  useEffect(() => {
    const updateDimensions = () => {
      if (svgRef.current?.parentElement) {
        setDimensions({
          width: svgRef.current.parentElement.clientWidth,
          height: Math.min(svgRef.current.parentElement.clientHeight, 420),
        });
      }
    };
    updateDimensions();
    window.addEventListener("resize", updateDimensions);
    return () => window.removeEventListener("resize", updateDimensions);
  }, []);

  useEffect(() => {
    if (!svgRef.current || keywords.length === 0) return;

    const { width, height } = dimensions;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    // Radius scale: sized by interest score
    const maxInterest = Math.max(...keywords.map((k) => k.current_interest), 1);
    const radiusScale = d3
      .scaleSqrt()
      .domain([0, maxInterest])
      .range([12, Math.min(width, height) / 8]);

    // Build nodes
    const nodes: BubbleNode[] = keywords.slice(0, 50).map((kw) => ({
      keyword: kw.keyword,
      category: kw.category,
      interest: kw.current_interest,
      velocity4w: kw.velocity_4w,
      velocity12w: kw.velocity_12w,
      radius: radiusScale(kw.current_interest),
      related_rising: kw.related_rising || [],
      x: width / 2 + (Math.random() - 0.5) * width * 0.4,
      y: height / 2 + (Math.random() - 0.5) * height * 0.4,
    }));

    // Defs for glow filter
    const defs = svg.append("defs");
    const filter = defs.append("filter").attr("id", "bubble-glow");
    filter
      .append("feGaussianBlur")
      .attr("stdDeviation", "4")
      .attr("result", "coloredBlur");
    const feMerge = filter.append("feMerge");
    feMerge.append("feMergeNode").attr("in", "coloredBlur");
    feMerge.append("feMergeNode").attr("in", "SourceGraphic");

    // Force simulation
    const simulation = d3
      .forceSimulation(nodes)
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("charge", d3.forceManyBody().strength(2))
      .force(
        "collision",
        d3.forceCollide<BubbleNode>().radius((d) => d.radius + 2).strength(0.9)
      )
      .force("x", d3.forceX(width / 2).strength(0.04))
      .force("y", d3.forceY(height / 2).strength(0.04))
      .alphaDecay(0.015);

    const g = svg.append("g");

    // Bubble groups
    const bubbles = g
      .selectAll("g.bubble")
      .data(nodes)
      .join("g")
      .attr("class", "bubble")
      .style("cursor", "pointer")
      .on("mouseenter", function (_, d) {
        setHoveredBubble(d.keyword);
        d3.select(this)
          .select("circle")
          .transition()
          .duration(200)
          .attr("r", d.radius * 1.08)
          .attr("stroke-width", 2);
      })
      .on("mouseleave", function (_, d) {
        setHoveredBubble(null);
        d3.select(this)
          .select("circle")
          .transition()
          .duration(200)
          .attr("r", d.radius)
          .attr("stroke-width", 1);
      })
      .on("click", (_, d) => {
        onKeywordClick?.(d.keyword);
      });

    // Circles
    bubbles
      .append("circle")
      .attr("r", 0)
      .attr("fill", (d) => {
        const color = colorMap[d.category] || "#94a3b8";
        return `${color}20`;
      })
      .attr("stroke", (d) => colorMap[d.category] || "#94a3b8")
      .attr("stroke-width", 1)
      .attr("opacity", (d) => {
        if (selectedKeyword && d.keyword !== selectedKeyword) return 0.15;
        return 0.85;
      })
      .attr("filter", (d) => (d.velocity4w > 100 ? "url(#bubble-glow)" : "none"))
      .transition()
      .duration(600)
      .delay((_, i) => i * 20)
      .attr("r", (d) => d.radius);

    // Labels (only for bubbles large enough)
    bubbles
      .filter((d) => d.radius > 20)
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "central")
      .attr("font-family", "Outfit, sans-serif")
      .attr("font-weight", "500")
      .attr("fill", (d) => colorMap[d.category] || "#94a3b8")
      .attr("opacity", 0)
      .each(function (d) {
        const el = d3.select(this);
        const maxChars = Math.floor(d.radius / 4.5);
        const label = d.keyword.length > maxChars
          ? d.keyword.slice(0, maxChars - 1) + "…"
          : d.keyword;
        el.attr("font-size", `${Math.max(9, Math.min(14, d.radius / 3.2))}px`);
        el.text(label);
      })
      .transition()
      .duration(600)
      .delay((_, i) => i * 20 + 300)
      .attr("opacity", (d) => {
        if (selectedKeyword && d.keyword !== selectedKeyword) return 0.15;
        return 0.9;
      });

    // Interest score under label for larger bubbles
    bubbles
      .filter((d) => d.radius > 32)
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "central")
      .attr("dy", "1.1em")
      .attr("font-family", "JetBrains Mono, monospace")
      .attr("font-size", "9px")
      .attr("font-weight", "600")
      .attr("fill", (d) => colorMap[d.category] || "#94a3b8")
      .attr("opacity", 0)
      .text((d) => d.interest.toString())
      .transition()
      .duration(600)
      .delay((_, i) => i * 20 + 400)
      .attr("opacity", (d) => {
        if (selectedKeyword && d.keyword !== selectedKeyword) return 0.1;
        return 0.5;
      });

    simulation.on("tick", () => {
      bubbles.attr("transform", (d) => {
        const x = Math.max(d.radius, Math.min(width - d.radius, d.x!));
        const y = Math.max(d.radius, Math.min(height - d.radius, d.y!));
        return `translate(${x}, ${y})`;
      });
    });

    return () => {
      simulation.stop();
    };
  }, [keywords, dimensions, onKeywordClick, colorMap, selectedKeyword]);

  // Tooltip data
  const hoveredData = hoveredBubble
    ? keywords.find((k) => k.keyword === hoveredBubble)
    : null;

  return (
    <div className="relative w-full h-full">
      <svg
        ref={svgRef}
        width={dimensions.width}
        height={dimensions.height}
        className="w-full h-full"
        role="img"
        aria-label="Keyword bubble chart visualization"
      />

      {/* Tooltip */}
      {hoveredData && (
        <div className="absolute top-4 right-4 glass-card p-3 min-w-[180px] pointer-events-none animate-fade-in z-10">
          <div
            className="font-display font-semibold text-sm mb-1"
            style={{
              color: colorMap[hoveredData.category] || "#94a3b8",
            }}
          >
            {hoveredData.keyword}
          </div>
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">
            {hoveredData.category}
          </div>
          <div className="space-y-1 text-xs text-slate-400">
            <div className="flex justify-between">
              <span>Interest:</span>
              <span className="font-mono text-white">
                {hoveredData.current_interest}/100
              </span>
            </div>
            <div className="flex justify-between">
              <span>4w velocity:</span>
              <span
                className="font-mono"
                style={{
                  color: hoveredData.velocity_4w >= 0 ? "#34D399" : "#EF4444",
                }}
              >
                {hoveredData.velocity_4w >= 0 ? "+" : ""}
                {hoveredData.velocity_4w}%
              </span>
            </div>
            <div className="flex justify-between">
              <span>12w velocity:</span>
              <span
                className="font-mono"
                style={{
                  color: hoveredData.velocity_12w >= 0 ? "#34D399" : "#EF4444",
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
