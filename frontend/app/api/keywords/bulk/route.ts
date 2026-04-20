import { NextRequest, NextResponse } from "next/server";
import { execute } from "@/lib/db";

interface BulkKeyword {
  keyword: string;
  category: string;
  subcategory?: string;
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { keywords } = body as { keywords: BulkKeyword[] };

    if (!Array.isArray(keywords) || keywords.length === 0) {
      return NextResponse.json(
        { error: "keywords array is required" },
        { status: 400 }
      );
    }

    let added = 0;
    let skipped = 0;
    const newCategories: string[] = [];
    const seenCategories = new Set<string>();

    for (const entry of keywords) {
      const kw = entry.keyword?.trim().toLowerCase();
      const cat = entry.category?.trim().toLowerCase();
      const sub = entry.subcategory?.trim().toLowerCase() || null;

      if (!kw || !cat) {
        skipped++;
        continue;
      }

      // Ensure category exists
      if (!seenCategories.has(cat)) {
        seenCategories.add(cat);
        const result = await execute(
          `INSERT INTO categories (name, is_active) VALUES (?, 1)
           ON CONFLICT(name) DO NOTHING`,
          [cat]
        );
        if ((result as any).rowsAffected > 0) {
          newCategories.push(cat);
        }
      }

      try {
        await execute(
          `INSERT INTO keywords (keyword, category, subcategory, is_active)
           VALUES (?, ?, ?, 1)
           ON CONFLICT(keyword) DO UPDATE SET
             category = excluded.category,
             subcategory = COALESCE(excluded.subcategory, keywords.subcategory),
             is_active = 1`,
          [kw, cat, sub]
        );
        added++;
      } catch {
        skipped++;
      }
    }

    return NextResponse.json({ added, skipped, newCategories });
  } catch (error) {
    console.error("Bulk keyword import error:", error);
    return NextResponse.json(
      { error: "Failed to import keywords" },
      { status: 500 }
    );
  }
}
