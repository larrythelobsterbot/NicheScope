import { NextRequest, NextResponse } from "next/server";
import { queryAll, execute } from "@/lib/db";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const region = searchParams.get("region");

  try {
    let sql = `SELECT * FROM suppliers`;
    const params: unknown[] = [];

    if (region) {
      sql += " WHERE region = ?";
      params.push(region);
    }

    sql += " ORDER BY quality_score DESC";

    const rows = await queryAll<{
      id: number;
      name: string;
      region: string;
      product_focus: string;
      price_range: string;
      moq: string;
      lead_time: string;
      quality_score: number;
      certifications: string;
      contact_url: string;
      notes: string;
    }>(sql, params);

    const suppliers = rows.map((row) => ({
      ...row,
      certifications: (() => {
        try {
          return JSON.parse(row.certifications || "[]");
        } catch {
          return [];
        }
      })(),
    }));

    return NextResponse.json({ suppliers });
  } catch (error) {
    console.error("Suppliers API error:", error);
    return NextResponse.json(
      { error: "Failed to fetch suppliers", suppliers: [] },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { name, region, product_focus, price_range, moq, lead_time, quality_score, certifications, contact_url, notes } = body;

    if (!name) {
      return NextResponse.json({ error: "Supplier name is required" }, { status: 400 });
    }

    await execute(
      `INSERT INTO suppliers (name, region, product_focus, price_range, moq, lead_time, quality_score, certifications, contact_url, notes)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        name,
        region || null,
        product_focus || null,
        price_range || null,
        moq || null,
        lead_time || null,
        quality_score || 5,
        JSON.stringify(certifications || []),
        contact_url || null,
        notes || null,
      ]
    );

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Add supplier error:", error);
    return NextResponse.json({ error: "Failed to add supplier" }, { status: 500 });
  }
}
