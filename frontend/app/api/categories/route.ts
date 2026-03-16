import { NextRequest, NextResponse } from "next/server";
import { queryAll, execute } from "@/lib/db";

export async function GET() {
  try {
    const categories = await queryAll<{
      id: number;
      name: string;
      color_override: string | null;
      sort_order: number;
      is_active: boolean;
    }>(
      `SELECT id, name, color_override, sort_order, is_active
       FROM categories
       WHERE is_active = 1
       ORDER BY sort_order ASC, name ASC`
    );

    return NextResponse.json({ categories });
  } catch (error) {
    console.error("Categories API error:", error);
    return NextResponse.json({ error: "Failed to fetch categories", categories: [] }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { name, color_override } = body;

    if (!name || typeof name !== "string") {
      return NextResponse.json({ error: "Category name is required" }, { status: 400 });
    }

    const maxOrder = await queryAll<{ max_order: number }>(
      "SELECT COALESCE(MAX(sort_order), 0) as max_order FROM categories"
    );
    const nextOrder = (maxOrder[0]?.max_order || 0) + 1;

    await execute(
      `INSERT INTO categories (name, color_override, sort_order, is_active)
       VALUES (?, ?, ?, 1)
       ON CONFLICT(name) DO UPDATE SET
         color_override = COALESCE(excluded.color_override, categories.color_override),
         is_active = 1`,
      [name.toLowerCase(), color_override || null, nextOrder]
    );

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Create category error:", error);
    return NextResponse.json({ error: "Failed to create category" }, { status: 500 });
  }
}
