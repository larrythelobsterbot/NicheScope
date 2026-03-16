"use client";

import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import { KeywordTrend } from "@/lib/types";
import { velocityToSize } from "@/lib/utils";

interface WordCloudProps {
  keywords: KeywordTrend[];
  onKeywordClick?: (keyword: string) => void;
  colorMap?: Record<string, string>;
  selectedKeyword?: string | null;
}

interface CloudWord {
  text: string;
  category: string;
  velocity: number;
  size: number;
  x: number;
  y: number;
  targetX: number;
  targetY: number;
}

export default function WordCloud({ keywords, onKeywordClick, colorMap = {}, selectedKeyword }: WordCloudProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });
  const [hoveredWord, setHoveredWord] = useState<string | null>(null);

  useEffect(() => {
    const updateDimensions = () => {
      if (svgRef.current?.parentElement) {
        setDimensions({
          width: svgRef.current.parentElement.clientWidth,
          height: Math.min(svgRef.current.parentElement.clientHeight, 500),
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

    // Prepare word data
    const words: CloudWord[] = keywords.slice(0, 40).map((kw, i) => {
      const angle = (i / keywords.length) * 2 * Math.PI;
      const radius = 100 + Math.random() * 120;
      return {
        text: kw.keyword,
        category: kw.category,
        velocity: kw.velocity_4w,
        size: velocityToSize(kw.velocity_4w, 12, 36),
        x: width / 2 + Math.cos(angle) * radius,
        y: height / 2 + Math.sin(angle) * radius,
        targetX: width / 2 + Math.cos(angle) * radius,
        targetY: height / 2 + Math.sin(angle) * radius,
      };
    });

    // Force simulation
    const simulation = d3
      .forceSimulation(words as d3.SimulationNodeDatum[] & CloudWord[])
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("charge", d3.forceManyBody().strength(-30))
      .force(
        "collision",
        d3.forceCollide<CloudWord>().radius((d) => d.size * 2.5)
      )
      .force("x", d3.forceX(width / 2).strength(0.05))
      .force("y", d3.forceY(height / 2).strength(0.05))
      .alphaDecay(0.02);

    const g = svg.append("g");

    // Add glow filter
    const defs = svg.append("defs");
    const filter = defs.append("filter").attr("id", "glow");
    filter
      .append("feGaussianBlur")
      .attr("stdDeviation", "3")
      .attr("result", "coloredBlur");
    const feMerge = filter.append("feMerge");
    feMerge.append("feMergeNode").attr("in", "coloredBlur");
    feMerge.append("feMergeNode").attr("in", "SourceGraphic");

    const textElements = g
      .selectAll("text")
      .data(words)
      .join("text")
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "central")
      .attr("font-family", "Outfit, sans-serif")
      .attr("font-weight", (d) => (d.velocity > 100 ? "700" : "500"))
      .attr("font-size", (d) => `${d.size}px`)
      .attr("fill", (d) => colorMap[d.category] || "#94a3b8")
      .attr("opacity", 0)
      .attr("cursor", "pointer")
      .attr("filter", (d) => (d.velocity > 200 ? "url(#glow)" : "none"))
      .text((d) => d.text)
      .on("mouseenter", function (event, d) {
        d3.select(this)
          .transition()
          .duration(200)
          .attr("font-size", `${d.size * 1.2}px`)
          .attr("opacity", 1);
        setHoveredWord(d.text);
      })
      .on("mouseleave", function (event, d) {
        const baseOpacity = selectedKeyword
          ? (d.text === selectedKeyword ? 1 : 0.2)
          : Math.max(0.4, Math.min(1, d.velocity / 100));
        d3.select(this)
          .transition()
          .duration(200)
          .attr("font-size", `${d.size}px`)
          .attr("opacity", baseOpacity);
        setHoveredWord(null);
      })
      .on("click", (event, d) => {
        onKeywordClick?.(d.text);
      });

    // Entrance animation
    textElements
      .transition()
      .duration(800)
      .delay((_, i) => i * 30)
      .attr("opacity", (d: any) => {
        if (selectedKeyword && d.text === selectedKeyword) return 1;
        if (selectedKeyword && d.text !== selectedKeyword) return 0.2;
        return Math.max(0.4, Math.min(1, d.velocity / 100));
      });

    simulation.on("tick", () => {
      textElements
        .attr("x", (d: any) => Math.max(60, Math.min(width - 60, d.x)))
        .attr("y", (d: any) => Math.max(30, Math.min(height - 30, d.y)));
    });

    return () => {
      simulation.stop();
    };
  }, [keywords, dimensions, onKeywordClick, colorMap, selectedKeyword]);

  // Tooltip data
  const hoveredData = hoveredWord
    ? keywords.find((k) => k.keyword === hoveredWord)
    : null;

  return (
    <div className="relative w-full h-full">
      <svg
        ref={svgRef}
        width={dimensions.width}
        height={dimensions.height}
        className="w-full h-full"
        role="img"
        aria-label="Keyword cloud visualization"
      />

      {/* Tooltip */}
      {hoveredData && (
        <div className="absolute top-4 right-4 glass-card p-3 min-w-[180px] pointer-events-none animate-fade-in">
          <div
            className="font-display font-semibold text-sm mb-1"
            style={{
              color: colorMap[hoveredData.category] || "#94a3b8",
            }}
          >
            {hoveredData.keyword}
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
