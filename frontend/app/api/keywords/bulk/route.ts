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

      // Queue for triage (see /api/import): junk-filtered Python-side, then
      // auto-approved by the daily triage. parent_keyword carries subcategory.
      try {
        await execute(
          `INSERT OR IGNORE INTO pending_keywords
             (keyword, suggested_category, source, parent_keyword,
              relevance_score, status)
           VALUES (?, ?, 'bulk_import', ?, 0.7, 'pending')`,
          [kw, cat, sub ?? ""]
        );
        added++;
      } catch {
        skipped++;
      }
    }

    return NextResponse.json({
      added,
      skipped,
      newCategories,
      note: "Queued for triage — junk-filtered and activated within 24h (daily 5:30 HKT).",
    });
  } catch (error) {
    console.error("Bulk keyword import error:", error);
    return NextResponse.json(
      { error: "Failed to import keywords" },
      { status: 500 }
    );
  }
}
