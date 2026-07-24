import assert from "node:assert/strict";
import test from "node:test";

import { deriveCollectorStatus } from "../lib/collectorHealth";

const now = new Date("2026-07-24T08:00:00Z");

test("collector failures outrank quota health", () => {
  assert.equal(
    deriveCollectorStatus({
      now,
      lastSuccess: "2026-07-24T07:00:00Z",
      lastStatus: "failure",
      consecutiveFailures: 1,
      consecutiveZeroRuns: 0,
      requestsToday: 0,
      dailyLimit: 100,
      staleAfterHours: 24,
    }),
    "error",
  );
});

test("collector is stale when its last success exceeds the schedule allowance", () => {
  assert.equal(
    deriveCollectorStatus({
      now,
      lastSuccess: "2026-07-22T07:59:59Z",
      lastStatus: "success",
      consecutiveFailures: 0,
      consecutiveZeroRuns: 0,
      requestsToday: 0,
      dailyLimit: null,
      staleAfterHours: 24,
    }),
    "stale",
  );
});

test("repeated zero-row runs produce a warning", () => {
  assert.equal(
    deriveCollectorStatus({
      now,
      lastSuccess: "2026-07-24T07:00:00Z",
      lastStatus: "success",
      consecutiveFailures: 0,
      consecutiveZeroRuns: 3,
      requestsToday: 0,
      dailyLimit: null,
      staleAfterHours: 24,
    }),
    "warning",
  );
});

test("quota exhaustion and low quota are reported", () => {
  const base = {
    now,
    lastSuccess: "2026-07-24T07:00:00Z",
    lastStatus: "success",
    consecutiveFailures: 0,
    consecutiveZeroRuns: 0,
    staleAfterHours: 24,
  };
  assert.equal(deriveCollectorStatus({ ...base, requestsToday: 100, dailyLimit: 100 }), "exhausted");
  assert.equal(deriveCollectorStatus({ ...base, requestsToday: 95, dailyLimit: 100 }), "warning");
});

test("on-demand collectors are not stale solely because they have never run", () => {
  assert.equal(
    deriveCollectorStatus({
      now,
      lastSuccess: null,
      lastStatus: null,
      consecutiveFailures: 0,
      consecutiveZeroRuns: 0,
      requestsToday: 0,
      dailyLimit: null,
      staleAfterHours: null,
    }),
    "never_run",
  );
});
