"use client";

import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import { geoNaturalEarth1, geoPath } from "d3-geo";

interface HeatMapProps {
  regionData: Record<string, number>;
  category?: string;
  colorMap?: Record<string, string>;
}

// CDN for world GeoJSON (Natural Earth simplified countries)
const WORLD_GEOJSON_URL =
  "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

/**
 * Normalize a country name for matching.
 * Handles common differences between Google Trends names and world-atlas names:
 *   "United States" ↔ "United States of America"
 *   "UK" ↔ "United Kingdom"
 *   "South Korea" ↔ "Korea, Republic of"
 */
function normalizeCountryName(name: string): string {
  const n = name.toLowerCase().trim();

  const aliases: Record<string, string> = {
    "united states": "united states of america",
    "usa": "united states of america",
    "us": "united states of america",
    "uk": "united kingdom",
    "south korea": "korea, republic of",
    "korea, south": "korea, republic of",
    "north korea": "korea, democratic people's republic of",
    "russia": "russian federation",
    "iran": "iran, islamic republic of",
    "vietnam": "viet nam",
    "czech republic": "czechia",
    "ivory coast": "côte d'ivoire",
    "bolivia": "bolivia, plurinational state of",
    "venezuela": "venezuela, bolivarian republic of",
    "tanzania": "tanzania, united republic of",
    "moldova": "moldova, republic of",
    "syria": "syrian arab republic",
    "laos": "lao people's democratic republic",
    "taiwan": "taiwan, province of china",
    "macedonia": "north macedonia",
    "swaziland": "eswatini",
    "burma": "myanmar",
    "east timor": "timor-leste",
    "cape verde": "cabo verde",
    "congo - kinshasa": "democratic republic of the congo",
    "congo - brazzaville": "congo",
  };

  return aliases[n] || n;
}

export default function HeatMap({
  regionData,
  category = "beauty",
  colorMap = {},
}: HeatMapProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [worldData, setWorldData] = useState<any>(null);
  const [tooltip, setTooltip] = useState<{
    text: string;
    x: number;
    y: number;
  } | null>(null);
  const color = colorMap[category] || "#94a3b8";

  useEffect(() => {
    const fetchWorld = async () => {
      try {
        const response = await fetch(WORLD_GEOJSON_URL);
        const topoData = await response.json();
        const { feature } = await import("topojson-client");
        const countries = feature(topoData, topoData.objects.countries);
        setWorldData(countries);
      } catch (error) {
        console.error("Failed to load world map:", error);
      }
    };
    fetchWorld();
  }, []);

  useEffect(() => {
    if (!svgRef.current || !worldData || Object.keys(regionData).length === 0)
      return;

    const svg = d3.select(svgRef.current);
    const width = svgRef.current.clientWidth || 600;
    const height = svgRef.current.clientHeight || 300;
    svg.selectAll("*").remove();

    // Build normalized name → value map (filter out zero values)
    const nameData: Record<string, number> = {};
    for (const [name, value] of Object.entries(regionData)) {
      if (value > 0) {
        nameData[normalizeCountryName(name)] = value;
      }
    }

    const values = Object.values(nameData);
    if (values.length === 0) {
      // No meaningful data after filtering
      const g = svg.append("g");
      const projection = geoNaturalEarth1()
        .fitSize([width, height], worldData as any)
        .translate([width / 2, height / 2]);
      const pathGenerator = geoPath().projection(projection);
      g.selectAll("path")
        .data((worldData as any).features)
        .join("path")
        .attr("d", pathGenerator as any)
        .attr("fill", "rgba(255,255,255,0.03)")
        .attr("stroke", "rgba(255,255,255,0.08)")
        .attr("stroke-width", 0.5);
      return;
    }

    const maxValue = Math.max(...values, 1);

    // Color scale — stronger contrast since most countries have value 0
    const colorScale = d3
      .scaleLinear<string>()
      .domain([0, maxValue * 0.25, maxValue * 0.6, maxValue])
      .range([
        "rgba(255,255,255,0.03)",
        `${color}30`,
        `${color}80`,
        color,
      ])
      .clamp(true);

    const projection = geoNaturalEarth1()
      .fitSize([width, height], worldData as any)
      .translate([width / 2, height / 2]);

    const pathGenerator = geoPath().projection(projection);

    const g = svg.append("g");

    const getValue = (feature: any): number | undefined => {
      const name = feature?.properties?.name;
      if (!name) return undefined;
      return nameData[normalizeCountryName(name)];
    };

    g.selectAll("path")
      .data((worldData as any).features)
      .join("path")
      .attr("d", pathGenerator as any)
      .attr("fill", (d: any) => {
        const value = getValue(d);
        return value !== undefined ? colorScale(value) : "rgba(255,255,255,0.03)";
      })
      .attr("stroke", "rgba(255,255,255,0.08)")
      .attr("stroke-width", 0.5)
      .attr("cursor", (d: any) =>
        getValue(d) !== undefined ? "pointer" : "default"
      )
      .on("mouseenter", function (event: MouseEvent, d: any) {
        const value = getValue(d);
        if (value !== undefined) {
          d3.select(this).attr("stroke", color).attr("stroke-width", 1.5);
          const name = d?.properties?.name || "Unknown";
          setTooltip({
            text: `${name}: ${value}`,
            x: event.offsetX,
            y: event.offsetY,
          });
        }
      })
      .on("mouseleave", function () {
        d3.select(this)
          .attr("stroke", "rgba(255,255,255,0.08)")
          .attr("stroke-width", 0.5);
        setTooltip(null);
      })
      .attr("opacity", 0)
      .transition()
      .duration(500)
      .delay((_, i) => i * 2)
      .attr("opacity", 1);
  }, [worldData, regionData, category, color]);

  if (Object.keys(regionData).length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        No geographic data available yet.
      </div>
    );
  }

  // Top countries summary for the legend
  const topCountries = Object.entries(regionData)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  return (
    <div className="relative w-full h-full flex flex-col">
      {topCountries.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap mb-2 shrink-0">
          <span className="text-[10px] text-slate-600 uppercase tracking-wider">
            Top regions:
          </span>
          {topCountries.map(([name, value]) => (
            <span
              key={name}
              className="text-[10px] text-slate-400 px-2 py-0.5 rounded-full bg-white/[0.03] border border-white/[0.04]"
            >
              {name}{" "}
              <span className="font-mono" style={{ color }}>
                {value}
              </span>
            </span>
          ))}
        </div>
      )}
      <div className="relative flex-1">
        <svg
          ref={svgRef}
          className="w-full h-full"
          role="img"
          aria-label="Geographic interest heatmap"
        />
        {tooltip && (
          <div
            className="absolute glass-card px-3 py-1.5 text-xs font-mono pointer-events-none z-10"
            style={{ left: tooltip.x + 10, top: tooltip.y - 30 }}
          >
            <span style={{ color }}>{tooltip.text}</span>
          </div>
        )}
      </div>
    </div>
  );
}
