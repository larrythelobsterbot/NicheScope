export type CollectorStatus =
  | "healthy"
  | "warning"
  | "exhausted"
  | "stale"
  | "error"
  | "never_run";

export interface CollectorStatusInput {
  now?: Date;
  lastSuccess: string | null;
  lastStatus: string | null;
  consecutiveFailures: number;
  consecutiveZeroRuns: number;
  requestsToday: number;
  dailyLimit: number | null;
  staleAfterHours: number | null;
}

function parseUtcTimestamp(value: string): number {
  const normalized = /(?:Z|[+-]\d\d:\d\d)$/.test(value)
    ? value
    : `${value.replace(" ", "T")}Z`;
  return new Date(normalized).getTime();
}

export function deriveCollectorStatus(input: CollectorStatusInput): CollectorStatus {
  const failed = input.lastStatus === "failed" || input.lastStatus === "failure";
  if (failed || input.consecutiveFailures > 0) return "error";

  if (!input.lastSuccess) return "never_run";

  if (input.staleAfterHours !== null) {
    const lastSuccessMs = parseUtcTimestamp(input.lastSuccess);
    const nowMs = (input.now ?? new Date()).getTime();
    if (!Number.isFinite(lastSuccessMs) || nowMs - lastSuccessMs > input.staleAfterHours * 3_600_000) {
      return "stale";
    }
  }

  if (input.dailyLimit !== null) {
    const remaining = input.dailyLimit - input.requestsToday;
    if (remaining <= 0) return "exhausted";
    if (remaining < input.dailyLimit * 0.1) return "warning";
  }

  if (input.consecutiveZeroRuns >= 3) return "warning";
  return "healthy";
}
