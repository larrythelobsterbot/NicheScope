#!/usr/bin/env python3
"""Initialize the NicheScope SQLite database with full schema."""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "nichescope.db")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.executescript("""
        -- Keywords we're tracking
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            subcategory TEXT,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        );

        -- Google Trends data points
        CREATE TABLE IF NOT EXISTS trend_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword_id INTEGER REFERENCES keywords(id),
            date DATE NOT NULL,
            interest_score INTEGER,
            related_rising TEXT,
            region_data TEXT,
            collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(keyword_id, date)
        );

        -- Amazon products we're tracking
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asin TEXT NOT NULL UNIQUE,
            title TEXT,
            category TEXT,
            brand TEXT,
            keyword_id INTEGER REFERENCES keywords(id),
            image_url TEXT,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        );

        -- Keepa/Amazon price + rank history
        CREATE TABLE IF NOT EXISTS product_history (
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
        );

        -- Competitor DTC stores
        CREATE TABLE IF NOT EXISTS competitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            domain TEXT UNIQUE,
            category TEXT,
            platform TEXT,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Traffic estimates for competitors
        CREATE TABLE IF NOT EXISTS competitor_traffic (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_id INTEGER REFERENCES competitors(id),
            month DATE NOT NULL,
            visits_estimate INTEGER,
            top_source TEXT,
            bounce_rate REAL,
            collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(competitor_id, month)
        );

        -- Supplier data
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            region TEXT,
            product_focus TEXT,
            price_range TEXT,
            price_low REAL,
            price_high REAL,
            moq TEXT,
            lead_time TEXT,
            quality_score INTEGER,
            certifications TEXT,
            contact_url TEXT,
            notes TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Niche scoring snapshots
        CREATE TABLE IF NOT EXISTS niche_scores (
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
        );

        -- Alerts log
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            severity TEXT,
            message TEXT NOT NULL,
            data TEXT,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            acknowledged BOOLEAN DEFAULT 0
        );

        -- TikTok trending data
        CREATE TABLE IF NOT EXISTS tiktok_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            hashtag TEXT,
            video_count INTEGER,
            view_count INTEGER,
            ad_count INTEGER,
            date DATE NOT NULL,
            collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(keyword, date)
        );

        -- Categories with custom colors (optional override of auto-assigned palette)
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color_override TEXT,
            repeat_score REAL,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Auto-discovered keywords pending user approval
        CREATE TABLE IF NOT EXISTS pending_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            suggested_category TEXT,
            source TEXT,
            parent_keyword TEXT,
            relevance_score REAL,
            discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            UNIQUE(keyword, suggested_category)
        );

        -- Discovery feedback loop: tracks source effectiveness
        CREATE TABLE IF NOT EXISTS discovery_stats (
            source TEXT NOT NULL,
            parent_keyword TEXT NOT NULL DEFAULT '',
            total_suggested INTEGER DEFAULT 0,
            total_approved INTEGER DEFAULT 0,
            total_rejected INTEGER DEFAULT 0,
            approval_rate REAL DEFAULT 0.0,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source, parent_keyword)
        );

        -- Indexes for common queries
        CREATE INDEX IF NOT EXISTS idx_trend_data_keyword_date ON trend_data(keyword_id, date);
        CREATE INDEX IF NOT EXISTS idx_product_history_product_date ON product_history(product_id, date);
        CREATE INDEX IF NOT EXISTS idx_niche_scores_category_date ON niche_scores(category, date);
        CREATE INDEX IF NOT EXISTS idx_alerts_type_sent ON alerts(type, sent_at);
        CREATE INDEX IF NOT EXISTS idx_tiktok_trends_keyword_date ON tiktok_trends(keyword, date);
        CREATE INDEX IF NOT EXISTS idx_keywords_category ON keywords(category);
        CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
    """)

    conn.commit()

    # Migrations: add columns that may not exist in older databases
    migrations = [
        "ALTER TABLE suppliers ADD COLUMN price_low REAL",
        "ALTER TABLE suppliers ADD COLUMN price_high REAL",
        "ALTER TABLE categories ADD COLUMN repeat_score REAL",
    ]
    for sql in migrations:
        try:
            cursor.execute(sql)
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.commit()
    conn.close()
    print(f"Database initialized at {os.path.abspath(DB_PATH)}")


if __name__ == "__main__":
    init_db()
