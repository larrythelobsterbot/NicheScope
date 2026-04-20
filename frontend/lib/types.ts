// Dynamic category — no longer hardcoded
export type Category = string;

export interface Keyword {
  id: number;
  keyword: string;
  category: string;
  subcategory: string | null;
  is_active: boolean;
}

export interface TrendDataPoint {
  date: string;
  interest_score: number;
  related_rising: string[] | null;
  region_data: Record<string, number> | null;
}

export interface KeywordTrend {
  keyword: string;
  category: string;
  subcategory: string | null;
  current_interest: number;
  velocity_4w: number;
  velocity_12w: number;
  history: TrendDataPoint[];
  related_rising: string[];
  region_data: Record<string, number>;
}

export interface Product {
  id: number;
  asin: string;
  title: string;
  category: string;
  brand: string;
  image_url: string;
  price: number | null;
  sales_rank: number | null;
  rating: number | null;
  review_count: number | null;
  growth: number;
}

export interface ProductHistory {
  date: string;
  price: number | null;
  sales_rank: number | null;
  review_count: number | null;
}

export interface Supplier {
  id: number;
  name: string;
  region: string;
  product_focus: string;
  price_range: string;
  moq: string;
  lead_time: string;
  quality_score: number;
  certifications: string[];
  contact_url: string;
  notes: string;
}

export interface NicheScore {
  category: string;
  date: string;
  trend_score: number;
  margin_score: number;
  competition_score: number;
  sourcing_score: number;
  content_score: number;
  repeat_purchase_score: number;
  overall_score: number;
}

export interface Alert {
  id: number;
  type: "breakout" | "price_drop" | "stock_out" | "trend_shift" | string;
  severity: "info" | "warning" | "critical" | string;
  message: string;
  data: Record<string, unknown>;
  sent_at: string;
  acknowledged: boolean;
}

export interface TikTokTrend {
  keyword: string;
  hashtag: string;
  video_count: number;
  view_count: number;
  ad_count: number;
  date: string;
}

export interface Competitor {
  id: number;
  name: string;
  domain: string;
  category: string;
  platform: string;
  visits_estimate: number;
  top_source: string;
  bounce_rate: number;
}

export interface PendingKeyword {
  id: number;
  keyword: string;
  suggested_category: string;
  source: string;
  parent_keyword: string;
  relevance_score: number;
  discovered_at: string;
  status: "pending" | "approved" | "rejected";
}

export interface StatsOverview {
  niches_tracked: number;
  avg_growth: number;
  best_margin: number;
  top_signal: string;
}
