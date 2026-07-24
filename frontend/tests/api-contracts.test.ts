import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function source(path: string): string {
  return readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
}

test("freshness API uses collection time and exposes the latest observed data period", () => {
  const route = source("app/api/health/route.ts");
  assert.match(route, /MAX\(collected_at\)[\s\S]*last_collection/);
  assert.match(route, /MAX\(date\)[\s\S]*latest_data_date/);
  assert.match(route, /dynamic\s*=\s*["']force-dynamic["']/);
});

test("database-backed operational routes are explicitly dynamic", () => {
  for (const path of [
    "app/api/collector-status/route.ts",
    "app/api/insights/route.ts",
    "app/api/niche-hunter/route.ts",
  ]) {
    assert.match(source(path), /dynamic\s*=\s*["']force-dynamic["']/, path);
  }
});

test("admin keyword route is paginated and no longer supports an unbounded all mode", () => {
  const route = source("app/api/keywords/route.ts");
  assert.doesNotMatch(route, /searchParams\.get\(["']all["']\)/);
  assert.match(route, /LIMIT \? OFFSET \?/);
  assert.match(route, /total_pages/);
});

test("pending queue route is paginated", () => {
  const route = source("app/api/pending/route.ts");
  assert.match(route, /LIMIT \? OFFSET \?/);
  assert.match(route, /total_pages/);
});

test("trend route bounds the keyword set and reports truncation metadata", () => {
  const route = source("app/api/trends/route.ts");
  assert.match(route, /MAX_TREND_KEYWORDS/);
  assert.match(route, /truncated/);
  assert.match(route, /available_keywords/);
});

test("dashboard center grid track can shrink without forcing page overflow", () => {
  const page = source("app/page.tsx");
  assert.match(page, /lg:grid-cols-\[240px_minmax\(0,1fr\)_320px\]/);
});
