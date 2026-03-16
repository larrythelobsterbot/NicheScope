import { NextResponse } from "next/server";
import { queryAll, queryOne } from "@/lib/db";

interface RateLimitRow {
  service: string;
  request_count: number;
  last_request_at: string | null;
}

interface CountRow {
  cnt: number;
}

const SERVICE_CONFIG: Record<string, { daily_limit: number | null; schedule: string }> = {
  google_trends: { daily_limit: 1400, schedule: "Daily 6am HKT" },
  keepa: { daily_limit: null, schedule: "Every 6 hours" },
  amazon_pa: { daily_limit: 8640, schedule: "On demand" },
  alibaba: { daily_limit: 100, schedule: "Weekly Mon 2am HKT" },
  tiktok: { daily_limit: 500, schedule: "Daily 8am HKT" },
  similarweb: { daily_limit: 50, schedule: "Weekly Wed 3am HKT" },
};

export async function GET() {
  try {
    // Get today's rate limit usage
    const rateLimits = await queryAll<RateLimitRow>(
      `SELECT service, request_count, last_request_at
       FROM rate_limits
       WHERE date = date('now')
       ORDER BY service`
    );

    const usageMap = new Map(rateLimits.map((r) => [r.service, r]));

    // Get latest collection timestamps from each data table
    const lastTrends = await queryOne<{ ts: string }>(
      "SELECT MAX(collected_at) as ts FROM trend_data"
    );
    const lastKeepa = await queryOne<{ ts: string }>(
      "SELECT MAX(collected_at) as ts FROM product_history"
    );
    const lastTiktok = await queryOne<{ ts: string }>(
      "SELECT MAX(collected_at) as ts FROM tiktok_trends"
    );
    const lastAlibaba = await queryOne<{ ts: string }>(
      "SELECT MAX(updated_at) as ts FROM suppliers"
    );
    const lastSimilarweb = await queryOne<{ ts: string }>(
      "SELECT MAX(collected_at) as ts FROM competitor_traffic"
    );

    const lastRunMap: Record<string, string | null> = {
      google_trends: lastTrends?.ts || null,
      keepa: lastKeepa?.ts || null,
      tiktok: lastTiktok?.ts || null,
      alibaba: lastAlibaba?.ts || null,
      similarweb: lastSimilarweb?.ts || null,
    };

    // Build collector status
    const collectors: Record<string, object> = {};
    for (const [service, config] of Object.entries(SERVICE_CONFIG)) {
      const usage = usageMap.get(service);
      const requestsToday = usage?.request_count || 0;
      const remaining = config.daily_limit ? config.daily_limit - requestsToday : null;

      let status = "healthy";
      if (config.daily_limit && remaining !== null) {
        if (remaining <= 0) status = "exhausted";
        else if (remaining < config.daily_limit * 0.1) status = "warning";
      }

      collectors[service] = {
        last_run: lastRunMap[service] || null,
        schedule: config.schedule,
        requests_today: requestsToday,
        daily_limit: config.daily_limit,
        remaining,
        status,
      };
    }

    // Total keywords
    const totalKw = await queryOne<CountRow>(
      "SELECT COUNT(*) as cnt FROM keywords WHERE is_active = 1"
    );

    return NextResponse.json({
      collectors,
      total_keywords: totalKw?.cnt || 0,
    });
  } catch (error) {
    console.error("Collector status error:", error);
    return NextResponse.json({ error: "Failed to fetch collector status" }, { status: 500 });
  }
}
