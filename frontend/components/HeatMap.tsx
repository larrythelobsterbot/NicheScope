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

  // ISO 3166-1 alpha-2 to numeric mapping for matching GeoJSON
  const ALPHA2_TO_NUMERIC: Record<string, string> = {
    US: "840", GB: "826", CA: "124", AU: "036", DE: "276", FR: "250",
    IN: "356", JP: "392", BR: "076", KR: "410", MX: "484", PH: "608",
    SG: "702", NZ: "554", NL: "528", IT: "380", ES: "724", SE: "752",
    ZA: "710", AE: "784", CN: "156", RU: "643", ID: "360", TH: "764",
    VN: "704", MY: "458", PK: "586", NG: "566", EG: "818", TR: "792",
    PL: "616", AR: "032", CO: "170", CL: "152", PE: "604", SA: "682",
    IE: "372", PT: "620", AT: "040", CH: "756", BE: "056", NO: "578",
    DK: "208", FI: "246", IL: "376", HK: "344", TW: "158",
  };

  // Country name lookup
  const COUNTRY_NAMES: Record<string, string> = {
    US: "United States", GB: "United Kingdom", CA: "Canada", AU: "Australia",
    DE: "Germany", FR: "France", IN: "India", JP: "Japan", BR: "Brazil",
    KR: "South Korea", MX: "Mexico", PH: "Philippines", SG: "Singapore",
    NZ: "New Zealand", NL: "Netherlands", IT: "Italy", ES: "Spain",
    SE: "Sweden", ZA: "South Africa", AE: "UAE", CN: "China", RU: "Russia",
  };

  useEffect(() => {
    // Fetch world GeoJSON (TopoJSON format from world-atlas)
    const fetchWorld = async () => {
      try {
        const response = await fetch(WORLD_GEOJSON_URL);
        const topoData = await response.json();
        // Convert TopoJSON to GeoJSON
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

    // Build numeric-to-value map
    const numericData: Record<string, number> = {};
    for (const [alpha2, value] of Object.entries(regionData)) {
      const numeric = ALPHA2_TO_NUMERIC[alpha2];
      if (numeric) numericData[numeric] = value;
    }

    const maxValue = Math.max(...Object.values(regionData), 1);

    // Color scale
    const colorScale = d3
      .scaleLinear<string>()
      .domain([0, maxValue * 0.3, maxValue])
      .range(["rgba(255,255,255,0.03)", `${color}40`, color])
      .clamp(true);

    // Projection
    const projection = geoNaturalEarth1()
      .fitSize([width, height], worldData)
      .translate([width / 2, height / 2]);

    const pathGenerator = geoPath().projection(projection);

    const g = svg.append("g");

    // Draw countries
    g.selectAll("path")
      .data(worldData.features)
      .join("path")
      .attr("d", pathGenerator as any)
      .attr("fill", (d: any) => {
        const id = d.id || d.properties?.id;
        const value = numericData[id];
        return value !== undefined ? colorScale(value) : "rgba(255,255,255,0.03)";
      })
      .attr("stroke", "rgba(255,255,255,0.08)")
      .attr("stroke-width", 0.5)
      .attr("cursor", (d: any) => {
        const id = d.id || d.properties?.id;
        return numericData[id] !== undefined ? "pointer" : "default";
      })
      .on("mouseenter", function (event: MouseEvent, d: any) {
        const id = d.id || d.properties?.id;
        const value = numericData[id];
        if (value !== undefined) {
          d3.select(this).attr("stroke", color).attr("stroke-width", 1.5);
          // Find alpha2 code from numeric
          const alpha2 = Object.entries(ALPHA2_TO_NUMERIC).find(
            ([, n]) => n === id
          )?.[0];
          const name = alpha2 ? COUNTRY_NAMES[alpha2] || alpha2 : id;
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
      // Entrance animation
      .attr("opacity", 0)
      .transition()
      .duration(600)
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

  return (
    <div className="relative w-full h-full">
      <svg ref={svgRef} className="w-full h-full" role="img" aria-label="Geographic interest heatmap" />
      {tooltip && (
        <div
          className="absolute glass-card px-3 py-1.5 text-xs font-mono pointer-events-none z-10"
          style={{ left: tooltip.x + 10, top: tooltip.y - 30 }}
        >
          <span style={{ color }}>{tooltip.text}</span>
        </div>
      )}
    </div>
  );
}
