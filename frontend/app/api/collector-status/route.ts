import { NextResponse } from "next/server";
import { queryAll, queryOne } from "@/lib/db";
import { deriveCollectorStatus } from "@/lib/collectorHealth";

export const dynamic = "force-dynamic";
export const revalidate = 0;

interface RateLimitRow {
  service: string;
  request_count: number;
  last_request_at: string | null;
}

interface HealthRow {
  collector_name: string;
  last_run: string | null;
  last_success: string | null;
  last_error: string | null;
  consecutive_failures: number | null;
  consecutive_zero_runs: number | null;
  items_collected: number | null;
  last_status: string | null;
}

interface CountRow {
  cnt: number;
}

interface ServiceConfig {
  healthKeys: string[];
  rateLimitKey?: string;
  dailyLimit: number | null;
  schedule: string;
  staleAfterHours: number | null;
}

const SERVICE_CONFIG: Record<string, ServiceConfig> = {
  google_trends: {
    healthKeys: ["google_trends"],
    dailyLimit: 1400,
    schedule: "Daily 6am HKT",
    staleAfterHours: 36,
  },
  amazon_bestsellers: {
    healthKeys: ["amazon_bestsellers", "keepa"],
    rateLimitKey: "keepa",
    dailyLimit: null,
    schedule: "Every 6 hours",
    staleAfterHours: 18,
  },
  amazon_pa: {
    healthKeys: ["amazon_pa"],
    dailyLimit: 8640,
    schedule: "On demand",
    staleAfterHours: null,
  },
  alibaba: {
    healthKeys: ["alibaba"],
    dailyLimit: 100,
    schedule: "Weekly Mon 2am HKT",
    staleAfterHours: 240,
  },
  youtube: {
    healthKeys: ["youtube"],
    dailyLimit: 10000,
    schedule: "Daily 8am HKT",
    staleAfterHours: 36,
  },
  similarweb: {
    healthKeys: ["competitor_traffic", "similarweb"],
    dailyLimit: 50,
    schedule: "Weekly Wed 3am HKT",
    staleAfterHours: 240,
  },
};

function newestHealth(rows: HealthRow[], aliases: string[]): HealthRow | undefined {
  return rows
    .filter((row) => aliases.includes(row.collector_name))
    .sort((left, right) => (right.last_run || "").localeCompare(left.last_run || ""))[0];
}

export async function GET() {
  try {
    const [rateLimits, healthRows] = await Promise.all([
      queryAll<RateLimitRow>(
        `SELECT service, request_count, last_request_at
         FROM rate_limits
         WHERE date = date('now')
         ORDER BY service`,
      ),
      queryAll<HealthRow>(
        `SELECT collector_name, last_run, last_success, last_error,
                consecutive_failures, consecutive_zero_runs,
                items_collected, last_status
         FROM collector_health
         ORDER BY collector_name`,
      ),
    ]);

    const usageMap = new Map(rateLimits.map((row) => [row.service, row]));
    const collectors: Record<string, object> = {};

    for (const [service, config] of Object.entries(SERVICE_CONFIG)) {
      const health = newestHealth(healthRows, config.healthKeys);
      const usage = usageMap.get(config.rateLimitKey || service);
      const requestsToday = usage?.request_count || 0;
      const remaining = config.dailyLimit === null ? null : Math.max(config.dailyLimit - requestsToday, 0);
      const consecutiveFailures = health?.consecutive_failures || 0;
      const consecutiveZeroRuns = health?.consecutive_zero_runs || 0;

      collectors[service] = {
        last_run: health?.last_run || null,
        last_success: health?.last_success || null,
        last_status: health?.last_status || null,
        last_error: health?.last_error || null,
        items_collected: health?.items_collected || 0,
        consecutive_failures: consecutiveFailures,
        consecutive_zero_runs: consecutiveZeroRuns,
        schedule: config.schedule,
        requests_today: requestsToday,
        daily_limit: config.dailyLimit,
        remaining,
        status: deriveCollectorStatus({
          lastSuccess: health?.last_success || null,
          lastStatus: health?.last_status || null,
          consecutiveFailures,
          consecutiveZeroRuns,
          requestsToday,
          dailyLimit: config.dailyLimit,
          staleAfterHours: config.staleAfterHours,
        }),
      };
    }

    const totalKw = await queryOne<CountRow>(
      "SELECT COUNT(*) as cnt FROM keywords WHERE is_active = 1",
    );

    return NextResponse.json(
      { collectors, total_keywords: totalKw?.cnt || 0, generated_at: new Date().toISOString() },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    console.error("Collector status error:", error);
    return NextResponse.json({ error: "Failed to fetch collector status" }, { status: 500 });
  }
}
