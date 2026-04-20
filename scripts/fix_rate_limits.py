#!/usr/bin/env python3
"""Fix the rate_limits table schema."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "nichescope.db")

conn = sqlite3.connect(DB_PATH)
conn.execute("DROP TABLE IF EXISTS rate_limits")
conn.execute("""
    CREATE TABLE rate_limits (
        service TEXT NOT NULL,
        date DATE NOT NULL,
        request_count INTEGER DEFAULT 0,
        last_request_at DATETIME,
        UNIQUE(service, date)
    )
""")
conn.commit()
conn.close()
print("rate_limits table recreated with correct schema")
