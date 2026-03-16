import { NextRequest, NextResponse } from "next/server";
import { queryAll, execute } from "@/lib/db";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const category = searchParams.get("category");
  const sort = searchParams.get("sort") || "growth";

  try {
    let sql = `
      SELECT p.id, p.asin, p.title, p.category, p.brand, p.image_url,
             ph_latest.price, ph_latest.sales_rank, ph_latest.rating,
             ph_latest.review_count, ph_latest.stock_status,
             ph_latest.buy_box_price,
             ph_prev.price as prev_price
      FROM products p
      LEFT JOIN (
        SELECT product_id, price, sales_rank, rating, review_count,
               stock_status, buy_box_price,
               ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY date DESC) as rn
        FROM product_history
      ) ph_latest ON p.id = ph_latest.product_id AND ph_latest.rn = 1
      LEFT JOIN (
        SELECT product_id, price,
               ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY date DESC) as rn
        FROM product_history
        WHERE date < datetime('now', '-7 days')
      ) ph_prev ON p.id = ph_prev.product_id AND ph_prev.rn = 1
      WHERE p.is_active = 1
    `;

    const params: unknown[] = [];
    if (category) {
      sql += " AND p.category = ?";
      params.push(category);
    }

    const rows = await queryAll<{
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
      stock_status: string | null;
      buy_box_price: number | null;
      prev_price: number | null;
    }>(sql, params);

    const products = rows.map((row) => {
      const growth =
        row.price && row.prev_price && row.prev_price > 0
          ? Math.round(((row.price - row.prev_price) / row.prev_price) * 1000) / 10
          : 0;

      return {
        id: row.id,
        asin: row.asin,
        title: row.title,
        category: row.category,
        brand: row.brand,
        image_url: row.image_url,
        price: row.price,
        sales_rank: row.sales_rank,
        rating: row.rating,
        review_count: row.review_count,
        stock_status: row.stock_status,
        buy_box_price: row.buy_box_price,
        growth,
      };
    });

    // Sort
    if (sort === "growth") {
      products.sort((a, b) => b.growth - a.growth);
    } else if (sort === "rank") {
      products.sort((a, b) => (a.sales_rank || Infinity) - (b.sales_rank || Infinity));
    } else if (sort === "price") {
      products.sort((a, b) => (a.price || 0) - (b.price || 0));
    }

    return NextResponse.json({ products });
  } catch (error) {
    console.error("Products API error:", error);
    return NextResponse.json({ error: "Failed to fetch products", products: [] }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { asin, title, category, brand } = body;

    if (!asin || !category) {
      return NextResponse.json({ error: "ASIN and category are required" }, { status: 400 });
    }

    await execute(
      `INSERT INTO products (asin, title, category, brand, is_active)
       VALUES (?, ?, ?, ?, 1)
       ON CONFLICT(asin) DO UPDATE SET
         title = COALESCE(excluded.title, products.title),
         category = excluded.category,
         brand = COALESCE(excluded.brand, products.brand),
         is_active = 1`,
      [asin.toUpperCase(), title || "", category.toLowerCase(), brand || ""]
    );

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Add product error:", error);
    return NextResponse.json({ error: "Failed to add product" }, { status: 500 });
  }
}
