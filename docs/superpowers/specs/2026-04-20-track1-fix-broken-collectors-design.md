# Track 1: Fix broken collectors

**Date:** 2026-04-20
**Status:** Draft — awaiting user review
**Scope:** NicheScope collector pipeline

## Context

NicheScope's scoring model (`collectors/analyzer.py`) depends on six signals: trend, margin, competition, sourcing, content, repeat-purchase. As of 2026-04-20, four of the upstream data sources are not landing data despite the scheduler reporting "success":

| Target table | Rows | Collector | Observed failure |
|---|---|---|---|
| `products` | 0 | keepa (amazon_pa) | Scheduler logs `"KEEPA_API_KEY not set"` every day; job never registered |
| `product_history` | 0 | keepa | Same as above |
| `competitor_traffic` | 0 | similarweb | Never appears in `collector_health`; job silently raises |
| `tiktok_trends` | 0 | tiktok_trends | TikTok Creative Center returns `code 40101: no permission` |

Consequences: `_calc_margin_score`, `_calc_competition_score`, and `_calc_content_score` fall back to hardcoded category defaults, so niche scoring is effectively driven by Google Trends velocity alone. Beauty-heavy keyword distribution (63%) amplifies this.

Additionally:
- `collector_health` records "success" if the function returns, regardless of rows written — the metric lies.
- `.env` loading at scheduler startup is silent on failure. If `.env` isn't present when PM2 starts the scheduler, conditional jobs like Keepa are never registered and re-registration requires a full restart.
- Telegram bot logs ~80 "credentials not configured" warnings per day despite `TELEGRAM_BOT_TOKEN` being present — symptom of the same env-loading issue in a different module.

## Goals

1. Each of `products`, `product_history`, `competitor_traffic`, and (the renamed) `content_trends` table receives new rows within one scheduler cycle after deploy.
2. Replacement for TikTok uses a signal that is actually available: YouTube Data API v3.
3. Env-loading failures surface loudly instead of silently disabling collectors.
4. Each fixed collector reports real success/failure to `collector_health`, including row-count delta per run.

## Non-goals (explicit)

- Rewriting `collector_health` table schema — covered by Track 2.
- Resolving SQLite `"database is locked"` contention — covered by Track 2.
- Rebalancing the scoring model to account for category imbalance — covered by Track 3.
- Restoring TikTok scraping. TikTok Creative Center is gated; we are moving to YouTube, not working around the block.
- Changes to `amazon_bestsellers` collector (reports success, no user-visible issue).

## Design

### Replace TikTok with YouTube Data API

New file: `collectors/youtube_trends.py`.

For each active keyword in the rotation budget:
1. `search.list(q=keyword, type=video, publishedAfter=now-30d, order=viewCount, maxResults=10)` — returns 10 video IDs.
2. `videos.list(id=...)` — returns view/like/comment counts.

Per-keyword signals stored:
- `video_count_7d` — count of returned videos published in last 7 days
- `video_count_30d` — count of returned videos published in last 30 days
- `total_views_30d` — sum of `viewCount` across the 10 videos
- `top_video_views` — max `viewCount`
- `avg_views_per_video` — mean `viewCount`

**Quota budget.** YouTube Data API v3 gives 10,000 quota units/day on the free tier. `search.list` = 100 units, `videos.list` = 1 unit per 50 IDs. Per keyword ≈ 101 units. Default daily budget: **top 80 keywords by most-recent niche score + 20 newest-approved keywords = 100 keywords/day ≈ 10,100 units.** Configurable via `YOUTUBE_DAILY_KEYWORD_BUDGET` in config.

Rotation is determined inside the collector so that over a week we cover the full active keyword list by score rank (tiered: top 80 every day, next 560 rotated across 7 days).

### Table rename: `tiktok_trends` → `content_trends`

New schema (`scripts/migrate_002_content_trends.py`, idempotent):
```sql
CREATE TABLE IF NOT EXISTS content_trends (
    id INTEGER PRIMARY KEY,
    keyword_id INTEGER NOT NULL,
    source TEXT NOT NULL,          -- 'youtube' for now; future: 'tiktok', 'instagram'
    collected_at DATETIME NOT NULL,
    video_count_7d INTEGER,
    video_count_30d INTEGER,
    total_views_30d INTEGER,
    top_video_views INTEGER,
    avg_views_per_video INTEGER,
    raw_json TEXT,
    FOREIGN KEY (keyword_id) REFERENCES keywords(id)
);
CREATE INDEX IF NOT EXISTS idx_content_trends_keyword_date
    ON content_trends (keyword_id, collected_at DESC);

-- Back-compat view so existing analyzer code doesn't break during rollout
CREATE VIEW IF NOT EXISTS tiktok_trends AS
    SELECT id, keyword_id, collected_at, total_views_30d AS view_count,
           video_count_30d AS video_count
    FROM content_trends WHERE source = 'youtube';
```

`analyzer.py::_calc_content_score` is updated to read from `content_trends` directly and interpret YouTube's signal (total views and 7-day publish velocity), not hashtag counts.

### Scheduler: env-loading correctness

Changes to `collectors/scheduler.py`:

1. **Fail-loud `.env` loading.** Replace `load_dotenv(path)` with an explicit check: if the resolved path does not exist, log ERROR and `sys.exit(1)`. No more silent passes.
2. **Per-run env check, not startup-gated.** Remove the `if os.getenv("KEEPA_API_KEY"):` guard around `scheduler.add_job`. Always register the job; let the job itself return early with a warning if the key is missing on that run. Same treatment for the Telegram daily-digest job.
3. **Shared wrapper `run_collector_job(name, fn)`.** All collector entrypoints return `(success: bool, items_written: int, error: str|None)` instead of raising or returning an int. The wrapper records `collector_health` with real counts. Minimum viable implementation — Track 2 will replace `collector_health` wholesale.

### Collector-level changes

**`keepa_collector.py::collect_products`**
- No code change required; fix is the scheduler-side env handling above.
- Add: if `get_tracked_asins()` returns empty dict, log a loud WARNING pointing to `scripts/seed_watchlist.py`.
- Return signature updated to `(bool, int, str|None)`.

**`similarweb.py::collect_competitor_traffic`**
- Wrap body in top-level try/except so the function never raises to the scheduler.
- Log every domain attempt at INFO; currently most attempts log only on exception.
- Add 5-second backoff on `429` and `5xx` responses with one retry.
- Persist `visits_estimate=0` as a real "low-traffic" row rather than skipping — SimilarWeb returning no data is itself a signal.
- Return `(bool, int, str|None)`.

**`alibaba_collector.py`**
- First step in implementation: dive into scheduler.log for recent alibaba runs to pinpoint why `suppliers` is stuck at 26 (= seed count).
- Two branches captured in the implementation plan:
  - **If bot-blocked:** add rotating User-Agent pool + 10s delay between requests + detect HTML-vs-JSON response and treat HTML as failure.
  - **If upsert bug:** fix `INSERT OR IGNORE` or conflict target so new suppliers are actually inserted.
- Return `(bool, int, str|None)`.

**`youtube_trends.py` (new)**
- Single module, pattern matched to `google_trends.py` for consistency.
- Uses `googleapiclient` (official Google SDK) — already a well-maintained dependency.
- Rate-limit wrapper modeled on `rate_limiter.GOOGLE_TRENDS`.
- Return `(bool, int, str|None)`.

### Configuration additions

In `collectors/config.py`:
- `YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")`
- `YOUTUBE_DAILY_KEYWORD_BUDGET = int(os.getenv("YOUTUBE_DAILY_KEYWORD_BUDGET", "100"))`
- `SCHEDULE["youtube"] = {"hour": 8, "minute": 0}` (HKT, replacing the `tiktok` slot)

New file: `.env.example` listing every key the project reads, with brief comments. This is the first time the project has documented its required env vars.

## Testing

Integration tests only — no HTTP mocks. Each test exercises the real collector against the real API with a single minimal input and asserts the target table gains ≥1 row. Tests gated on API-key presence using `pytest.skip` so they don't fail on a machine without the key.

- `tests/test_youtube_trends.py` — fetch trends for `"press on nails"`, assert `content_trends` row count increases.
- `tests/test_keepa_collector.py` — query one ASIN, assert `products` row appears.
- `tests/test_similarweb.py` — fetch traffic for `"etsy.com"`, assert `competitor_traffic` row appears (even if `visits_estimate=0`).
- `tests/test_alibaba_collector.py` — run for one category, assert `suppliers` row count either increases or stays flat with a logged explanation.

Smoke test: `python scripts/refresh_now.py --only youtube,similarweb,keepa,alibaba` must exit 0 and print row counts for each target table. The script itself gains a `--only` flag as part of this work.

## Rollout

1. Apply migration `migrate_002_content_trends.py` (idempotent — safe to re-run).
2. Deploy new collector files and scheduler changes.
3. Restart scheduler via PM2 (`pm2 restart collectors`).
4. Manually: `python scripts/refresh_now.py --only youtube,similarweb,keepa,alibaba`.
5. Verify `collector_health` has fresh rows with `items_written > 0` for each.
6. Wait 24h. Success criteria: all four target tables have rows with timestamps within the last 24h.

If any collector still writes zero rows after step 4, that collector is removed from success criteria and tracked as a follow-up. The other collectors do not block the deploy.

## Risks

- **YouTube quota exceeded.** Mitigation: budget is configurable; default of 100 keywords/day leaves 0 buffer. If we consistently hit quota, drop to 80/day. Alternative: request a quota increase (free but manual review).
- **YouTube views are not directly comparable to TikTok hashtag counts.** `_calc_content_score` needs a recalibration. In scope for this track: swap the inputs and pick a reasonable normalization (0-100 scale). Out of scope: treating this as a signal upgrade — that's Track 3.
- **Similarweb public endpoint is undocumented** and can disappear without warning. Mitigation: treat `visits_estimate=0` as valid data rather than skipping, so historical trend continuity is preserved even during outages.
- **Alibaba bot-detection.** Branch resolution is in the implementation plan. If both branches fail (block is permanent + no bug), we accept that supplier counts stay capped and document it as a known limitation rather than extending this spec.

## Open questions for user review

1. YouTube quota budget of 100 keywords/day — acceptable, or would you rather cover fewer (top 50) with more signals per keyword?
2. Acceptable to fail-loud (scheduler exits) if `.env` is missing? Currently silent — a change in operator behavior.
3. Any preference on whether `alibaba_collector.py` gets scope in this track or gets deferred to a follow-up if the log dive shows the issue is bot-blocking rather than a code bug?
