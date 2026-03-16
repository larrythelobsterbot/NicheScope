import { NextRequest, NextResponse } from "next/server";
import { queryAll, execute } from "@/lib/db";

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get("file") as File | null;

    if (!file) {
      return NextResponse.json({ error: "No file provided" }, { status: 400 });
    }

    const text = await file.text();
    const lines = text.split("\n").filter((l) => l.trim());

    if (lines.length < 2) {
      return NextResponse.json({ error: "CSV must have a header row and at least one data row" }, { status: 400 });
    }

    // Parse header
    const headers = lines[0].split(",").map((h) => h.trim().toLowerCase());
    const catIdx = headers.indexOf("category");
    const kwIdx = headers.indexOf("keyword");
    const subIdx = headers.indexOf("subcategory");

    if (catIdx === -1 || kwIdx === -1) {
      return NextResponse.json(
        { error: "CSV must have 'category' and 'keyword' columns" },
        { status: 400 }
      );
    }

    // Get existing categories
    const existingCats = await queryAll<{ name: string }>(
      "SELECT name FROM categories WHERE is_active = 1"
    );
    const existingCatSet = new Set(existingCats.map((c) => c.name));

    let added = 0;
    let skipped = 0;
    const newCategories: string[] = [];

    // Process each row
    for (let i = 1; i < lines.length; i++) {
      const cols = parseCSVLine(lines[i]);
      const category = (cols[catIdx] || "").trim().toLowerCase();
      const keyword = (cols[kwIdx] || "").trim().toLowerCase();
      const subcategory = subIdx >= 0 ? (cols[subIdx] || "").trim() || null : null;

      if (!category || !keyword) {
        skipped++;
        continue;
      }

      // Create category if new
      if (!existingCatSet.has(category)) {
        const maxOrder = await queryAll<{ max_order: number }>(
          "SELECT COALESCE(MAX(sort_order), 0) as max_order FROM categories"
        );
        const nextOrder = (maxOrder[0]?.max_order || 0) + 1;

        await execute(
          `INSERT INTO categories (name, sort_order, is_active) VALUES (?, ?, 1)
           ON CONFLICT(name) DO UPDATE SET is_active = 1`,
          [category, nextOrder]
        );
        existingCatSet.add(category);
        newCategories.push(category);
      }

      // Insert keyword (skip duplicates)
      try {
        const result = await execute(
          `INSERT INTO keywords (keyword, category, subcategory, is_active)
           VALUES (?, ?, ?, 1)
           ON CONFLICT(keyword) DO NOTHING`,
          [keyword, category, subcategory]
        );
        if (result.rowsAffected > 0) {
          added++;
        } else {
          skipped++;
        }
      } catch {
        skipped++;
      }
    }

    return NextResponse.json({ added, skipped, newCategories });
  } catch (error) {
    console.error("Import error:", error);
    return NextResponse.json({ error: "Failed to import CSV" }, { status: 500 });
  }
}

/** Parse a CSV line handling quoted fields */
function parseCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
      result.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }
  result.push(current.trim());
  return result;
}
