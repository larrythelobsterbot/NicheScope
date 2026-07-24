import { NextResponse } from "next/server";
import { queryOne } from "@/lib/db";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  try {
    const stats = await queryOne<{
      total_data_points: number;
      last_collection: string | null;
      latest_data_date: string | null;
      total_keywords: number;
      total_categories: number;
    }>(`
      SELECT
        (SELECT COUNT(*) FROM trend_data) as total_data_points,
        (SELECT MAX(collected_at) FROM trend_data) as last_collection,
        (SELECT MAX(date) FROM trend_data) as latest_data_date,
        (SELECT COUNT(*) FROM keywords WHERE is_active = 1) as total_keywords,
        (SELECT COUNT(DISTINCT category) FROM keywords WHERE is_active = 1) as total_categories
    `);

    return NextResponse.json(
      {
        status: "ok",
        total_data_points: stats?.total_data_points || 0,
        last_collection: stats?.last_collection || null,
        latest_data_date: stats?.latest_data_date || null,
        total_keywords: stats?.total_keywords || 0,
        total_categories: stats?.total_categories || 0,
        generated_at: new Date().toISOString(),
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    console.error("Health check error:", error);
    return NextResponse.json(
      { status: "error", error: "Database unavailable" },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
