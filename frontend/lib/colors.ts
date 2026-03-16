/**
 * Dynamic category color system.
 * Mirrors the Python CATEGORY_PALETTE from config.py.
 */

export const CATEGORY_PALETTE = [
  "#FF6B8A",  // pink (beauty default)
  "#A78BFA",  // purple (jewelry default)
  "#34D399",  // green (travel default)
  "#FBBF24",  // amber
  "#60A5FA",  // blue
  "#FB923C",  // orange
  "#F472B6",  // hot pink
  "#2DD4BF",  // teal
  "#C084FC",  // violet
  "#4ADE80",  // lime
  "#E879F9",  // fuchsia
  "#38BDF8",  // sky
  "#A3E635",  // yellow-green
  "#F97316",  // deep orange
  "#818CF8",  // indigo
];

export interface CategoryInfo {
  name: string;
  color_override: string | null;
  sort_order: number;
  is_active: boolean;
}

/**
 * Build a color map from categories list.
 * Uses color_override if set, otherwise auto-assigns from palette by index.
 */
export function getCategoryColorMap(
  categories: CategoryInfo[]
): Record<string, string> {
  const colorMap: Record<string, string> = {};
  categories.forEach((cat, i) => {
    colorMap[cat.name] = cat.color_override || CATEGORY_PALETTE[i % CATEGORY_PALETTE.length];
  });
  return colorMap;
}

/**
 * Get a single category's color from map, with fallback.
 */
export function getCategoryColor(
  category: string,
  colorMap: Record<string, string>
): string {
  return colorMap[category] || "#94A3B8";
}

/**
 * Generate a CSS text-shadow glow for a given hex color.
 */
export function getGlowStyle(color: string): React.CSSProperties {
  return {
    textShadow: `0 0 20px ${color}99, 0 0 40px ${color}4D`,
  };
}

/**
 * Generate a subtle bg tint style for a category pill.
 */
export function getCategoryBgStyle(color: string, active: boolean): React.CSSProperties {
  if (!active) return {};
  return {
    backgroundColor: `${color}25`,
    color: color,
  };
}
