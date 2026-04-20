#!/usr/bin/env node
/**
 * NicheScope Query CLI
 * =====================
 * Read-only access to the NicheScope database for research queries.
 * Designed to be invoked by Claude Code skills or any script.
 *
 * Usage:
 *   nichescope-query <command> [options]
 *
 * Commands:
 *   hot         Find keywords with the highest recent velocity
 *   search      Full-text search across tracked keywords
 *   trend       Show detailed trend history for one keyword
 *   clusters    Show emerging niche clusters from pending discoveries
 *   scores      Show niche scores per category
 *   categories  List all active categories with keyword counts
 *   pending     List recent pending keyword discoveries
 *   stats       Show high-level dashboard stats
 *   export      Bulk-export active keywords in CSV or JSON
 *
 * Common flags:
 *   --format table|json|csv      (default: table)
 *   --limit N                    (default varies)
 *   --category <name>            filter by category
 *   --help                       show this message
 *
 * Database path can be overridden with NICHESCOPE_DB_PATH env var.
 * Default: /home/muffinman/NicheScope/data/nichescope.db
 */

import { createClient } from "@libsql/client";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_PATH =
  process.env.NICHESCOPE_DB_PATH ||
  path.join(__dirname, "..", "data", "nichescope.db");

const db = createClient({ url: `file:${DB_PATH}` });

// ───────────────────────────────────────────────────────────
// Argument parsing
// ───────────────────────────────────────────────────────────

function parseArgs(argv) {
  const args = { _: [], flags: {} };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const key = a.slice(2);
      const next = argv[i + 1];
      if (next && !next.startsWith("--")) {
        args.flags[key] = next;
        i++;
      } else {
        args.flags[key] = true;
      }
    } else {
      args._.push(a);
    }
  }
  return args;
}

// ───────────────────────────────────────────────────────────
// Output formatters
// ───────────────────────────────────────────────────────────

function asCsv(rows) {
  if (rows.length === 0) return "";
  const cols = Object.keys(rows[0]);
  const esc = (v) => {
    if (v === null || v === undefined) return "";
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
}

function asTable(rows) {
  if (rows.length === 0) return "(no rows)";
  const cols = Object.keys(rows[0]);
  // Per-column caps: the first column (usually a keyword) gets a generous
  // 70 chars so beauty product names don't get chopped — truncation there
  // defeats the purpose of the tool. Other columns cap at 40.
  const widths = cols.map((c, idx) => {
    const cap = idx === 0 ? 70 : 40;
    return Math.min(
      Math.max(c.length, ...rows.map((r) => String(r[c] ?? "").length)),
      cap
    );
  });
  const pad = (s, w) => {
    const str = String(s ?? "");
    return str.length > w ? str.slice(0, w - 1) + "…" : str.padEnd(w);
  };
  const sep = widths.map((w) => "─".repeat(w)).join("─┼─");
  const header = cols.map((c, i) => pad(c, widths[i])).join(" │ ");
  const body = rows
    .map((r) => cols.map((c, i) => pad(r[c], widths[i])).join(" │ "))
    .join("\n");
  return `${header}\n${sep}\n${body}`;
}

function output(rows, format = "table") {
  if (format === "json") {
    console.log(JSON.stringify(rows, null, 2));
  } else if (format === "csv") {
    console.log(asCsv(rows));
  } else {
    console.log(asTable(rows));
    console.log(`\n${rows.length} row${rows.length === 1 ? "" : "s"}`);
  }
}

// ───────────────────────────────────────────────────────────
// Commands
// ───────────────────────────────────────────────────────────

const commands = {
  async hot(args) {
    // Top keywords by 4-week velocity within active keywords that have data
    const limit = parseInt(args.flags.limit || "20", 10);
    const category = args.flags.category;
    const days = parseInt(args.flags.days || "28", 10);
    const minInterest = parseInt(args.flags["min-interest"] || "10", 10);

    const sql = `
      SELECT k.keyword, k.category, k.subcategory,
             td_now.interest_score as current,
             COALESCE(td_prev.interest_score, 1) as prev,
             ROUND(((CAST(td_now.interest_score AS REAL) /
                     MAX(COALESCE(td_prev.interest_score, 1), 1)) - 1) * 100, 1) as velocity_pct
      FROM keywords k
      JOIN (
        SELECT keyword_id, interest_score,
               ROW_NUMBER() OVER (PARTITION BY keyword_id ORDER BY date DESC) as rn
        FROM trend_data
      ) td_now ON k.id = td_now.keyword_id AND td_now.rn = 1
      LEFT JOIN (
        SELECT keyword_id, interest_score,
               ROW_NUMBER() OVER (PARTITION BY keyword_id ORDER BY date DESC) as rn
        FROM trend_data
        WHERE date <= date('now', '-' || ? || ' days')
      ) td_prev ON k.id = td_prev.keyword_id AND td_prev.rn = 1
      WHERE k.is_active = 1
        AND td_now.interest_score >= ?
        ${category ? "AND k.category = ?" : ""}
      ORDER BY velocity_pct DESC
      LIMIT ?
    `;

    const params = [days, minInterest];
    if (category) params.push(category);
    params.push(limit);

    const rows = await db.execute({ sql, args: params });
    output(
      rows.rows.map((r) => ({
        keyword: r.keyword,
        category: r.category,
        subcategory: r.subcategory || "",
        interest: r.current,
        velocity: `${r.velocity_pct > 0 ? "+" : ""}${r.velocity_pct}%`,
      })),
      args.flags.format
    );
  },

  async search(args) {
    const query = args._[1];
    if (!query) {
      console.error("Usage: nichescope-query search <query> [--category X] [--limit N]");
      process.exit(1);
    }

    const limit = parseInt(args.flags.limit || "30", 10);
    const category = args.flags.category;
    const status = args.flags.status || "active"; // active|pending|all

    const where = [];
    const params = [`%${query.toLowerCase()}%`];

    if (status === "active" || status === "all") {
      let sql = `
        SELECT k.keyword, k.category, k.subcategory,
               COALESCE(td.interest_score, 0) as interest,
               'active' as status
        FROM keywords k
        LEFT JOIN (
          SELECT keyword_id, interest_score,
                 ROW_NUMBER() OVER (PARTITION BY keyword_id ORDER BY date DESC) as rn
          FROM trend_data
        ) td ON k.id = td.keyword_id AND td.rn = 1
        WHERE k.is_active = 1 AND LOWER(k.keyword) LIKE ?
        ${category ? "AND k.category = ?" : ""}
        ORDER BY interest DESC
        LIMIT ?
      `;
      const qargs = [...params];
      if (category) qargs.push(category);
      qargs.push(limit);
      const r = await db.execute({ sql, args: qargs });
      let results = r.rows.map((row) => ({
        keyword: row.keyword,
        category: row.category,
        subcategory: row.subcategory || "",
        interest: row.interest,
        status: row.status,
      }));

      if (status === "all") {
        const psql = `
          SELECT keyword, suggested_category as category, source, relevance_score
          FROM pending_keywords
          WHERE status = 'pending' AND LOWER(keyword) LIKE ?
          ${category ? "AND suggested_category = ?" : ""}
          ORDER BY relevance_score DESC
          LIMIT ?
        `;
        const pargs = [...params];
        if (category) pargs.push(category);
        pargs.push(limit);
        const p = await db.execute({ sql: psql, args: pargs });
        results = results.concat(
          p.rows.map((row) => ({
            keyword: row.keyword,
            category: row.category,
            subcategory: "",
            interest: Math.round((row.relevance_score || 0) * 100),
            status: `pending (${row.source})`,
          }))
        );
      }
      output(results, args.flags.format);
    } else if (status === "pending") {
      const psql = `
        SELECT keyword, suggested_category as category, source, parent_keyword,
               relevance_score, discovered_at
        FROM pending_keywords
        WHERE status = 'pending' AND LOWER(keyword) LIKE ?
        ${category ? "AND suggested_category = ?" : ""}
        ORDER BY relevance_score DESC
        LIMIT ?
      `;
      const pargs = [...params];
      if (category) pargs.push(category);
      pargs.push(limit);
      const p = await db.execute({ sql: psql, args: pargs });
      output(p.rows, args.flags.format);
    }
  },

  async trend(args) {
    const keyword = args._.slice(1).join(" ");
    if (!keyword) {
      console.error("Usage: nichescope-query trend <keyword>");
      process.exit(1);
    }

    const kw = await db.execute({
      sql: "SELECT id, keyword, category, subcategory FROM keywords WHERE LOWER(keyword) = LOWER(?) LIMIT 1",
      args: [keyword],
    });

    if (kw.rows.length === 0) {
      console.log(`No tracked keyword matches "${keyword}"`);
      console.log("Try: nichescope-query search '<partial>' to find it");
      return;
    }

    const k = kw.rows[0];
    const history = await db.execute({
      sql: "SELECT date, interest_score, related_rising FROM trend_data WHERE keyword_id = ? ORDER BY date DESC LIMIT 20",
      args: [k.id],
    });

    const current = history.rows[0]?.interest_score || 0;
    const fourW = history.rows[3]?.interest_score || history.rows[history.rows.length - 1]?.interest_score || 1;
    const twelveW = history.rows[11]?.interest_score || history.rows[history.rows.length - 1]?.interest_score || 1;
    const v4 = Math.round(((current / Math.max(fourW, 1)) - 1) * 1000) / 10;
    const v12 = Math.round(((current / Math.max(twelveW, 1)) - 1) * 1000) / 10;

    let related = [];
    if (history.rows.length > 0 && history.rows[0].related_rising) {
      try {
        related = JSON.parse(history.rows[0].related_rising);
      } catch {}
    }

    if (args.flags.format === "json") {
      console.log(
        JSON.stringify(
          {
            keyword: k.keyword,
            category: k.category,
            subcategory: k.subcategory,
            current_interest: current,
            velocity_4w_pct: v4,
            velocity_12w_pct: v12,
            history: history.rows.map((r) => ({
              date: r.date,
              interest: r.interest_score,
            })),
            related_rising: related,
          },
          null,
          2
        )
      );
      return;
    }

    console.log(`━━━ ${k.keyword} ━━━`);
    console.log(`Category:     ${k.category}${k.subcategory ? ` / ${k.subcategory}` : ""}`);
    console.log(`Interest now: ${current}/100`);
    console.log(`4w velocity:  ${v4 > 0 ? "+" : ""}${v4}%`);
    console.log(`12w velocity: ${v12 > 0 ? "+" : ""}${v12}%`);
    console.log(`\nLast 20 data points:`);
    console.log(asTable(history.rows.map((r) => ({ date: r.date, interest: r.interest_score }))));
    if (related.length > 0) {
      console.log(`\nRelated rising queries:`);
      for (const r of related.slice(0, 10)) console.log(`  · ${r}`);
    }
  },

  async clusters(args) {
    const limit = parseInt(args.flags.limit || "15", 10);
    const minSize = parseInt(args.flags["min-size"] || "3", 10);
    const category = args.flags.category;
    const days = parseInt(args.flags.days || "30", 10);

    const sql = `
      SELECT parent_keyword, suggested_category as category,
             COUNT(*) as size,
             COUNT(DISTINCT source) as sources,
             ROUND(AVG(relevance_score), 2) as avg_relevance,
             MAX(discovered_at) as newest
      FROM pending_keywords
      WHERE status = 'pending'
        AND parent_keyword != ''
        AND discovered_at >= datetime('now', '-' || ? || ' days')
        ${category ? "AND suggested_category = ?" : ""}
      GROUP BY parent_keyword
      HAVING size >= ?
      ORDER BY size DESC, avg_relevance DESC
      LIMIT ?
    `;
    const params = [days];
    if (category) params.push(category);
    params.push(minSize, limit);

    const r = await db.execute({ sql, args: params });
    output(r.rows, args.flags.format);
  },

  async scores(args) {
    const sort = args.flags.sort || "overall";
    const validSorts = [
      "overall",
      "trend",
      "margin",
      "competition",
      "sourcing",
      "content",
      "repeat",
    ];
    if (!validSorts.includes(sort)) {
      console.error(`Invalid --sort. Pick one of: ${validSorts.join(", ")}`);
      process.exit(1);
    }
    const sortCol = sort === "repeat" ? "repeat_purchase_score" : `${sort}_score`;

    const r = await db.execute({
      sql: `
        SELECT category,
               ROUND(overall_score, 1) as overall,
               ROUND(trend_score, 1) as trend,
               ROUND(margin_score, 1) as margin,
               ROUND(competition_score, 1) as competition,
               ROUND(sourcing_score, 1) as sourcing,
               ROUND(content_score, 1) as content,
               ROUND(repeat_purchase_score, 1) as repeat_purchase
        FROM niche_scores
        WHERE date = (SELECT MAX(date) FROM niche_scores)
        ORDER BY ${sortCol} DESC
      `,
      args: [],
    });
    output(r.rows, args.flags.format);
  },

  async categories(args) {
    const r = await db.execute({
      sql: `
        SELECT c.name,
               COUNT(CASE WHEN k.is_active = 1 THEN 1 END) as active_keywords,
               COUNT(DISTINCT k.subcategory) as subcategories
        FROM categories c
        LEFT JOIN keywords k ON k.category = c.name
        WHERE c.is_active = 1
        GROUP BY c.name
        ORDER BY active_keywords DESC
      `,
      args: [],
    });
    output(r.rows, args.flags.format);
  },

  async pending(args) {
    const limit = parseInt(args.flags.limit || "20", 10);
    const category = args.flags.category;
    const source = args.flags.source;

    const where = ["status = 'pending'"];
    const params = [];
    if (category) {
      where.push("suggested_category = ?");
      params.push(category);
    }
    if (source) {
      where.push("source = ?");
      params.push(source);
    }
    params.push(limit);

    const sql = `
      SELECT keyword,
             suggested_category as category,
             source,
             parent_keyword,
             ROUND(relevance_score, 2) as relevance,
             DATE(discovered_at) as found
      FROM pending_keywords
      WHERE ${where.join(" AND ")}
      ORDER BY discovered_at DESC, relevance_score DESC
      LIMIT ?
    `;
    const r = await db.execute({ sql, args: params });
    output(r.rows, args.flags.format);
  },

  async stats(args) {
    const kws = await db.execute("SELECT COUNT(*) as cnt FROM keywords WHERE is_active = 1");
    const tdp = await db.execute("SELECT COUNT(*) as cnt FROM trend_data");
    const pend = await db.execute("SELECT COUNT(*) as cnt FROM pending_keywords WHERE status = 'pending'");
    const cats = await db.execute("SELECT COUNT(*) as cnt FROM categories WHERE is_active = 1");
    const latest = await db.execute("SELECT MAX(date) as d FROM trend_data");
    const sources = await db.execute(
      "SELECT source, COUNT(*) as cnt FROM pending_keywords WHERE status = 'pending' GROUP BY source ORDER BY cnt DESC"
    );
    const topMover = await db.execute(`
      SELECT k.keyword, td_now.interest_score as cur,
             ROUND(((CAST(td_now.interest_score AS REAL) /
                    MAX(COALESCE(td_prev.interest_score, 1), 1)) - 1) * 100, 1) as v
      FROM keywords k
      JOIN (
        SELECT keyword_id, interest_score,
               ROW_NUMBER() OVER (PARTITION BY keyword_id ORDER BY date DESC) as rn
        FROM trend_data
      ) td_now ON k.id = td_now.keyword_id AND td_now.rn = 1
      LEFT JOIN (
        SELECT keyword_id, interest_score,
               ROW_NUMBER() OVER (PARTITION BY keyword_id ORDER BY date DESC) as rn
        FROM trend_data
        WHERE date <= date('now', '-28 days')
      ) td_prev ON k.id = td_prev.keyword_id AND td_prev.rn = 1
      WHERE k.is_active = 1 AND td_now.interest_score >= 20
      ORDER BY v DESC
      LIMIT 1
    `);

    if (args.flags.format === "json") {
      console.log(
        JSON.stringify(
          {
            active_keywords: kws.rows[0].cnt,
            trend_data_points: tdp.rows[0].cnt,
            pending_discoveries: pend.rows[0].cnt,
            active_categories: cats.rows[0].cnt,
            latest_collection_date: latest.rows[0].d,
            discovery_sources: sources.rows,
            top_mover: topMover.rows[0] || null,
          },
          null,
          2
        )
      );
      return;
    }

    console.log("━━━ NicheScope stats ━━━");
    console.log(`  Active keywords:      ${kws.rows[0].cnt}`);
    console.log(`  Trend data points:    ${tdp.rows[0].cnt}`);
    console.log(`  Pending discoveries:  ${pend.rows[0].cnt}`);
    console.log(`  Active categories:    ${cats.rows[0].cnt}`);
    console.log(`  Latest collection:    ${latest.rows[0].d || "none"}`);
    console.log("\n  Pending by source:");
    for (const r of sources.rows) {
      console.log(`    ${String(r.cnt).padStart(5)}  ${r.source}`);
    }
    if (topMover.rows[0]) {
      const t = topMover.rows[0];
      console.log(`\n  Top mover (4w): ${t.keyword} (+${t.v}%, interest ${t.cur})`);
    }
  },

  async export(args) {
    const category = args.flags.category;
    const format = args.flags.format || "csv";
    const activeOnly = args.flags["active-only"] !== "false";

    const sql = `
      SELECT k.keyword, k.category, k.subcategory, k.is_active,
             COALESCE(td.interest_score, 0) as current_interest
      FROM keywords k
      LEFT JOIN (
        SELECT keyword_id, interest_score,
               ROW_NUMBER() OVER (PARTITION BY keyword_id ORDER BY date DESC) as rn
        FROM trend_data
      ) td ON k.id = td.keyword_id AND td.rn = 1
      WHERE 1=1
      ${activeOnly ? "AND k.is_active = 1" : ""}
      ${category ? "AND k.category = ?" : ""}
      ORDER BY k.category, k.subcategory, current_interest DESC
    `;
    const params = [];
    if (category) params.push(category);

    const r = await db.execute({ sql, args: params });
    // Force format (not a table here — too much data)
    if (format === "json") {
      console.log(JSON.stringify(r.rows, null, 2));
    } else {
      console.log(asCsv(r.rows));
    }
  },

  help() {
    const usage = `
NicheScope Query CLI
━━━━━━━━━━━━━━━━━━━━
Read-only research queries against the NicheScope database.

Usage:
  nichescope-query <command> [options]

Commands:
  hot         Top keywords by 4-week velocity (what's rising fastest)
  search <q>  Find keywords by text match
  trend <kw>  Detailed trend history + related queries for one keyword
  clusters    Emerging niche clusters from pending discoveries
  scores      Category-level niche scores
  categories  List categories with keyword counts
  pending     Recent keyword discoveries (not yet approved)
  stats       High-level dashboard summary
  export      Bulk-export active keywords (csv or json)

Common flags:
  --category <name>       filter by category name
  --subcategory <name>    filter by subcategory
  --limit N               max rows to return
  --format table|json|csv (default: table)
  --help                  show this message

Examples:
  nichescope-query hot --category beauty --limit 10
  nichescope-query search "pdrn"
  nichescope-query trend "numbuzin no 9"
  nichescope-query clusters --category beauty --min-size 5
  nichescope-query scores --sort margin
  nichescope-query stats
  nichescope-query export --category beauty --format csv > keywords.csv

Database: ${DB_PATH}
Override with NICHESCOPE_DB_PATH env var.
`;
    console.log(usage.trim());
  },
};

// ───────────────────────────────────────────────────────────
// Main
// ───────────────────────────────────────────────────────────

const args = parseArgs(process.argv.slice(2));
const cmd = args._[0];

if (!cmd || cmd === "help" || args.flags.help) {
  commands.help();
  process.exit(0);
}

if (!(cmd in commands)) {
  console.error(`Unknown command: ${cmd}`);
  console.error("Run 'nichescope-query help' for usage.");
  process.exit(1);
}

try {
  await commands[cmd](args);
} catch (e) {
  console.error(`Error: ${e.message}`);
  if (process.env.DEBUG) console.error(e.stack);
  process.exit(1);
}
