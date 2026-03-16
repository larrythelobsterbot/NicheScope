"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Legend,
} from "recharts";
import { Supplier } from "@/lib/types";

interface MarginAnalysisProps {
  suppliers: Supplier[];
  selectedCategory?: string | null;
  retailMultipliers?: Record<string, number>;
}

interface MarginData {
  name: string;
  region: string;
  landed_cost: number;
  retail_price: number;
  margin: number;
  margin_pct: number;
}

function parseSupplierCost(priceRange: string): number {
  const match = priceRange.match(/\$?([\d.]+)/);
  if (!match) return 0;
  const parts = priceRange.match(/\$?([\d.]+).*?\$?([\d.]+)/);
  if (parts) {
    return (parseFloat(parts[1]) + parseFloat(parts[2])) / 2;
  }
  return parseFloat(match[1]);
}

// Expanded retail multipliers — covers more product types
const DEFAULT_RETAIL_MULTIPLIERS: Record<string, number> = {
  // Beauty
  "nail stickers": 4.5,
  "gel strips": 5.0,
  "false eyelashes": 6.0,
  "lashes": 6.0,
  "skincare": 5.0,
  "makeup": 4.5,
  "cosmetic": 4.5,
  "hair accessories": 4.0,
  "serum": 5.5,
  // Jewelry
  "body jewelry": 5.0,
  "septum rings": 4.0,
  "necklace": 4.5,
  "bracelet": 4.0,
  "earrings": 4.5,
  "rings": 4.0,
  "pendant": 5.0,
  // Travel
  "packing cubes": 3.5,
  "travel pillow": 3.0,
  "cosmetic bags": 4.0,
  "suitcase": 2.5,
  "luggage": 2.5,
  "backpack": 3.0,
  "passport holder": 4.0,
  // Pets
  "pet collar": 3.5,
  "pet toy": 4.0,
  "pet bandana": 5.0,
  "dog leash": 3.5,
  "cat toy": 4.5,
  // Home
  "candle": 5.0,
  "wall art": 4.0,
  "organizer": 3.5,
  "kitchen gadget": 3.5,
  "storage": 3.0,
  // Fitness
  "resistance bands": 4.0,
  "yoga mat": 3.0,
  "gym accessories": 3.5,
  "water bottle": 3.5,
  // Tech
  "phone case": 5.0,
  "charger": 3.5,
  "earbuds": 3.0,
  "cable": 4.0,
  // Default
  default: 4.0,
};

export default function MarginAnalysis({ suppliers, selectedCategory, retailMultipliers }: MarginAnalysisProps) {
  const multipliers = { ...DEFAULT_RETAIL_MULTIPLIERS, ...retailMultipliers };

  function getRetailMultiplier(productFocus: string): number {
    for (const [key, mult] of Object.entries(multipliers)) {
      if (key !== "default" && productFocus.toLowerCase().includes(key)) return mult;
    }
    return multipliers.default || 4.0;
  }

  const marginData: MarginData[] = suppliers.map((s) => {
    const cost = parseSupplierCost(s.price_range);
    const multiplier = getRetailMultiplier(s.product_focus);
    const retail = cost * multiplier;
    const shippingEstimate = cost * 0.3; // ~30% of product cost
    const landedCost = cost + shippingEstimate;
    const margin = retail - landedCost;
    const marginPct = retail > 0 ? (margin / retail) * 100 : 0;

    return {
      name: s.name.length > 20 ? s.name.slice(0, 20) + "..." : s.name,
      region: s.region,
      landed_cost: Math.round(landedCost * 100) / 100,
      retail_price: Math.round(retail * 100) / 100,
      margin: Math.round(margin * 100) / 100,
      margin_pct: Math.round(marginPct * 10) / 10,
    };
  });

  marginData.sort((a, b) => b.margin_pct - a.margin_pct);

  if (marginData.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        No supplier data available yet. Seed the database to see margin analysis.
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Chart */}
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={marginData}
            layout="vertical"
            margin={{ top: 5, right: 20, left: 5, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis
              type="number"
              stroke="#475569"
              tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }}
              tickFormatter={(v) => `$${v}`}
            />
            <YAxis
              dataKey="name"
              type="category"
              width={130}
              stroke="#475569"
              tick={{ fontSize: 10, fontFamily: "Outfit" }}
            />
            <Tooltip
              contentStyle={{
                background: "#12121c",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "8px",
                fontFamily: "JetBrains Mono",
                fontSize: "11px",
              }}
              formatter={(value: unknown, name: unknown) => [`$${Number(value).toFixed(2)}`, String(name)]}
            />
            <Legend wrapperStyle={{ fontSize: "11px" }} />
            <Bar dataKey="landed_cost" name="Landed Cost" stackId="a" fill="#EF4444" radius={[0, 0, 0, 0]} />
            <Bar dataKey="margin" name="Margin" stackId="a" fill="#34D399" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Top 3 opportunity cards */}
      <div className="grid grid-cols-3 gap-3 mt-4">
        {marginData.slice(0, 3).map((item, i) => (
          <div key={i} className="glass-card p-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
              #{i + 1} Opportunity
            </div>
            <div className="font-display text-sm font-medium truncate">{item.name}</div>
            <div className="font-mono text-lg font-bold text-emerald-400">
              {item.margin_pct}%
            </div>
            <div className="text-[10px] text-slate-500">
              ${item.landed_cost} cost / ${item.retail_price} retail
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
