import { NextResponse } from "next/server";
import { queryOne } from "@/lib/db";

export async function GET() {
  try {
    const stats = await queryOne<{
      total_data_points: number;
      last_collection: string;
      total_keywords: number;
      total_categories: number;
    }>(`
      SELECT
        (SELECT COUNT(*) FROM trend_data) as total_data_points,
        (SELECT MAX(date) FROM trend_data) as last_collection,
        (SELECT COUNT(*) FROM keywords WHERE is_active = 1) as total_keywords,
        (SELECT COUNT(DISTINCT category) FROM keywords WHERE is_active = 1) as total_categories
    `);

    return NextResponse.json({
      status: "ok",
      total_data_points: stats?.total_data_points || 0,
      last_collection: stats?.last_collection || null,
      total_keywords: stats?.total_keywords || 0,
      total_categories: stats?.total_categories || 0,
    });
  } catch (error) {
    console.error("Health check error:", error);
    return NextResponse.json(
      { status: "error", error: "Database unavailable" },
      { status: 500 }
    );
  }
}
