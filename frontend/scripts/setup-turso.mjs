#!/usr/bin/env node
/**
 * Setup Turso database: creates all tables, indexes, and seeds initial data.
 *
 * Usage:
 *   set TURSO_DATABASE_URL=libsql://...
 *   set TURSO_AUTH_TOKEN=...
 *   node scripts/setup-turso.mjs
 */

import { createClient } from "@libsql/client";

const url = process.env.TURSO_DATABASE_URL;
const authToken = process.env.TURSO_AUTH_TOKEN;

if (!url) {
  console.error("ERROR: Set TURSO_DATABASE_URL environment variable first.");
  process.exit(1);
}
if (!authToken) {
  console.error("ERROR: Set TURSO_AUTH_TOKEN environment variable first.");
  process.exit(1);
}

const client = createClient({ url, authToken });

// ── Schema ──────────────────────────────────────────────────────────────────

const SCHEMA_STATEMENTS = [
  `CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    subcategory TEXT,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
  )`,
  `CREATE TABLE IF NOT EXISTS trend_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id INTEGER REFERENCES keywords(id),
    date DATE NOT NULL,
    interest_score INTEGER,
    related_rising TEXT,
    region_data TEXT,
    collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(keyword_id, date)
  )`,
  `CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT NOT NULL UNIQUE,
    title TEXT,
    category TEXT,
    brand TEXT,
    keyword_id INTEGER REFERENCES keywords(id),
    image_url TEXT,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
  )`,
  `CREATE TABLE IF NOT EXISTS product_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(id),
    date DATETIME NOT NULL,
    price REAL,
    sales_rank INTEGER,
    rating REAL,
    review_count INTEGER,
    offers_count INTEGER,
    buy_box_price REAL,
    stock_status TEXT,
    collected_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )`,
  `CREATE TABLE IF NOT EXISTS competitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    domain TEXT UNIQUE,
    category TEXT,
    platform TEXT,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )`,
  `CREATE TABLE IF NOT EXISTS competitor_traffic (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_id INTEGER REFERENCES competitors(id),
    month DATE NOT NULL,
    visits_estimate INTEGER,
    top_source TEXT,
    bounce_rate REAL,
    collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(competitor_id, month)
  )`,
  `CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    region TEXT,
    product_focus TEXT,
    price_range TEXT,
    moq TEXT,
    lead_time TEXT,
    quality_score INTEGER,
    certifications TEXT,
    contact_url TEXT,
    notes TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )`,
  `CREATE TABLE IF NOT EXISTS niche_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    date DATE NOT NULL,
    trend_score REAL,
    margin_score REAL,
    competition_score REAL,
    sourcing_score REAL,
    content_score REAL,
    repeat_purchase_score REAL,
    overall_score REAL,
    UNIQUE(category, date)
  )`,
  `CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    severity TEXT,
    message TEXT NOT NULL,
    data TEXT,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    acknowledged BOOLEAN DEFAULT 0
  )`,
  `CREATE TABLE IF NOT EXISTS tiktok_trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    hashtag TEXT,
    video_count INTEGER,
    view_count INTEGER,
    ad_count INTEGER,
    date DATE NOT NULL,
    collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(keyword, date)
  )`,
  `CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color_override TEXT,
    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )`,
  `CREATE TABLE IF NOT EXISTS pending_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    suggested_category TEXT,
    source TEXT,
    parent_keyword TEXT,
    relevance_score REAL,
    discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'pending',
    UNIQUE(keyword, suggested_category)
  )`,
  // Indexes
  `CREATE INDEX IF NOT EXISTS idx_trend_data_keyword_date ON trend_data(keyword_id, date)`,
  `CREATE INDEX IF NOT EXISTS idx_product_history_product_date ON product_history(product_id, date)`,
  `CREATE INDEX IF NOT EXISTS idx_niche_scores_category_date ON niche_scores(category, date)`,
  `CREATE INDEX IF NOT EXISTS idx_alerts_type_sent ON alerts(type, sent_at)`,
  `CREATE INDEX IF NOT EXISTS idx_tiktok_trends_keyword_date ON tiktok_trends(keyword, date)`,
  `CREATE INDEX IF NOT EXISTS idx_keywords_category ON keywords(category)`,
  `CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)`,
];

// ── Seed Data ───────────────────────────────────────────────────────────────

const CATEGORIES = [
  { name: "beauty", order: 0 },
  { name: "jewelry", order: 1 },
  { name: "travel", order: 2 },
  { name: "home", order: 3 },
  { name: "fashion", order: 4 },
  { name: "pets", order: 5 },
];

const KEYWORDS = {
  beauty: [
    "nail stickers", "gel nail strips", "semi cured gel nails",
    "nail wraps", "nail art stickers", "false eyelashes",
    "cosmetic bags", "K-beauty nails", "3D nail art",
    "press on nails", "DIY manicure",
  ],
  jewelry: [
    "septum rings", "nickel free jewelry", "hypoallergenic earrings",
    "body jewelry", "titanium jewelry", "surgical steel jewelry",
    "charms pendants", "chain belts", "nose rings",
    "nickel free earrings", "body piercing jewelry",
  ],
  travel: [
    "packing cubes", "compression packing cubes", "travel pillow",
    "memory foam travel pillow", "luggage organizer",
    "hardshell suitcase", "canvas tote bag",
    "travel accessories", "carry on luggage",
  ],
  home: [
    "home storage solutions", "dining room decor", "bookshelves",
    "ceiling decor", "pendant lights", "table centerpieces",
  ],
  fashion: [
    "bodysuits", "skirts trending", "water sports clothing",
    "sleep shorts",
  ],
  pets: [
    "dog plush toys", "dog bowls", "dog waste bags",
    "pet aquariums terrariums",
  ],
};

const COMPETITORS = {
  beauty: [
    { name: "Glamnetic", domain: "glamnetic.com", platform: "shopify" },
    { name: "Ohora", domain: "ohora.com", platform: "shopify" },
    { name: "Dashing Diva", domain: "dashingdiva.com", platform: "shopify" },
  ],
  jewelry: [
    { name: "AMYO Jewelry", domain: "amyojewelry.com", platform: "shopify" },
    { name: "Mejuri", domain: "mejuri.com", platform: "shopify" },
    { name: "BodyCandy", domain: "bodycandy.com", platform: "custom" },
  ],
  travel: [
    { name: "BAGAIL", domain: "bagail.com", platform: "shopify" },
    { name: "BAGSMART", domain: "bagsmart.com", platform: "shopify" },
    { name: "Eagle Creek", domain: "eaglecreek.com", platform: "custom" },
  ],
};

const SUPPLIERS = [
  { name: "Shanghai Huizi Cosmetics", region: "Shanghai", product_focus: "Semi-cured gel nail strips, Korean-style designs", price_range: "$0.62-2.25/unit", moq: "500 pcs", lead_time: "10-14 days", quality_score: 8, certifications: '["GMP"]', contact_url: "https://huizi.en.alibaba.com", notes: "Strong for branded gel strip lines. Korean aesthetic." },
  { name: "Guangzhou Yimei Printing", region: "Guangzhou", product_focus: "Nail stickers, tattoos, face gems. Full OEM.", price_range: "$0.12-0.15/unit", moq: "1000 pcs", lead_time: "10-14 days", quality_score: 9, certifications: '["FSC","GMPC","ISO22716","SEDEX","Disney FAMA"]', contact_url: "https://tiebeauty.en.alibaba.com", notes: "Factory since 1999. Best compliance certs in the space." },
  { name: "Colorful Fashion Jewelry Co.", region: "Yiwu", product_focus: "Nickel-free fashion jewelry, charms, earrings, body jewelry", price_range: "$0.10-1.50/pc", moq: "12 pcs/style", lead_time: "5-7 days", quality_score: 8, certifications: '["SGS","CPSIA","EU REACH"]', contact_url: "https://www.clfjewelry.com", notes: "17 yrs experience. Lead/nickel/cadmium-free certified. Low MOQ." },
  { name: "Yiwu J And D Jewelry", region: "Yiwu", product_focus: "Body jewelry, septum rings, nose studs", price_range: "$0.30-2.00/pc", moq: "100 pcs", lead_time: "7-14 days", quality_score: 8, certifications: '["SGS"]', contact_url: "", notes: "39% reorder rate (highest in category). Good for bulk." },
  { name: "Dongguan Happy Beauty / Cool Jewelry", region: "Dongguan", product_focus: "Surgical steel jewelry, PVD plating, custom designs", price_range: "$0.50-3.00/pc", moq: "100 pcs", lead_time: "15-25 days", quality_score: 9, certifications: '["ASTM F136"]', contact_url: "", notes: "2-3hr response time. Near-perfect reviews. Premium tier." },
  { name: "Dongguan I Am Flying Industry", region: "Dongguan", product_focus: "Travel pillows, memory foam, inflatable, hooded designs", price_range: "$2.00-5.00/unit", moq: "50 pcs", lead_time: "15-20 days", quality_score: 8, certifications: '["CE","OEKO-TEX"]', contact_url: "https://iamflying.en.alibaba.com", notes: "Specialist travel pillow manufacturer. Custom logo OEM." },
  { name: "Quanzhou Maxtop Group", region: "Quanzhou", product_focus: "Compression packing cubes, luggage organizers, travel bags", price_range: "$1.50-4.00/set", moq: "100 sets", lead_time: "18-25 days", quality_score: 7, certifications: "[]", contact_url: "", notes: "Large-scale travel accessories. Good for volume orders." },
  { name: "Guangzhou Zhengxiang Printing", region: "Guangzhou", product_focus: "Gel nail wraps, no-UV-lamp stickers, custom designs", price_range: "$0.08-0.12/unit", moq: "10 pcs", lead_time: "7-14 days", quality_score: 7, certifications: "[]", contact_url: "https://showyboo.en.alibaba.com", notes: "Ultra low MOQ (10 pcs). Great for design testing." },
];

// ── Execute ─────────────────────────────────────────────────────────────────

async function run() {
  console.log("Connecting to Turso...");
  console.log(`  URL: ${url}`);

  // 1. Create schema
  console.log("\n[1/4] Creating tables and indexes...");
  for (const sql of SCHEMA_STATEMENTS) {
    await client.execute(sql);
  }
  console.log(`  Created ${SCHEMA_STATEMENTS.length} tables/indexes.`);

  // 2. Seed categories
  console.log("\n[2/4] Seeding categories...");
  for (const cat of CATEGORIES) {
    await client.execute({
      sql: "INSERT OR IGNORE INTO categories (name, sort_order) VALUES (?, ?)",
      args: [cat.name, cat.order],
    });
  }
  console.log(`  Seeded ${CATEGORIES.length} categories.`);

  // 3. Seed keywords
  console.log("\n[3/4] Seeding keywords...");
  let kwCount = 0;
  for (const [category, keywords] of Object.entries(KEYWORDS)) {
    for (const kw of keywords) {
      await client.execute({
        sql: "INSERT OR IGNORE INTO keywords (keyword, category) VALUES (?, ?)",
        args: [kw, category],
      });
      kwCount++;
    }
  }
  console.log(`  Seeded ${kwCount} keywords across ${Object.keys(KEYWORDS).length} categories.`);

  // 4. Seed competitors
  console.log("\n[4/5] Seeding competitors...");
  let compCount = 0;
  for (const [category, comps] of Object.entries(COMPETITORS)) {
    for (const comp of comps) {
      await client.execute({
        sql: "INSERT OR IGNORE INTO competitors (name, domain, category, platform) VALUES (?, ?, ?, ?)",
        args: [comp.name, comp.domain, category, comp.platform],
      });
      compCount++;
    }
  }
  console.log(`  Seeded ${compCount} competitors.`);

  // 5. Seed suppliers
  console.log("\n[5/5] Seeding suppliers...");
  for (const sup of SUPPLIERS) {
    await client.execute({
      sql: `INSERT OR IGNORE INTO suppliers
            (name, region, product_focus, price_range, moq, lead_time,
             quality_score, certifications, contact_url, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      args: [
        sup.name, sup.region, sup.product_focus, sup.price_range,
        sup.moq, sup.lead_time, sup.quality_score, sup.certifications,
        sup.contact_url, sup.notes,
      ],
    });
  }
  console.log(`  Seeded ${SUPPLIERS.length} suppliers.`);

  console.log("\nDone! Turso database is ready.");
}

run().catch((err) => {
  console.error("Setup failed:", err);
  process.exit(1);
});
