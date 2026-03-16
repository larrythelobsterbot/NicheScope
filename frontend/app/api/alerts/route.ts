import { NextRequest, NextResponse } from "next/server";
import { queryAll, execute } from "@/lib/db";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const limit = parseInt(searchParams.get("limit") || "50", 10);
  const type = searchParams.get("type");

  try {
    let sql = `
      SELECT id, type, severity, message, data, sent_at, acknowledged
      FROM alerts
      WHERE 1=1
    `;
    const params: unknown[] = [];

    if (type) {
      sql += " AND type = ?";
      params.push(type);
    }

    sql += " ORDER BY sent_at DESC LIMIT ?";
    params.push(limit);

    const alerts = await queryAll<{
      id: number;
      type: string;
      severity: string;
      message: string;
      data: string | null;
      sent_at: string;
      acknowledged: boolean;
    }>(sql, params);

    const parsed = alerts.map((a) => ({
      ...a,
      data: a.data ? JSON.parse(a.data) : {},
    }));

    return NextResponse.json({ alerts: parsed });
  } catch (error) {
    console.error("Alerts API error:", error);
    return NextResponse.json({ error: "Failed to fetch alerts", alerts: [] }, { status: 500 });
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const { id, acknowledged } = body;

    if (!id) {
      return NextResponse.json({ error: "Alert ID is required" }, { status: 400 });
    }

    await execute("UPDATE alerts SET acknowledged = ? WHERE id = ?", [acknowledged ? 1 : 0, id]);
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Update alert error:", error);
    return NextResponse.json({ error: "Failed to update alert" }, { status: 500 });
  }
}
