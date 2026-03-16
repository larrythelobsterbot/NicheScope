#!/usr/bin/env python3
"""
Run once: python scripts/seed_watchlist.py
Populates keywords, competitors, suppliers, and categories tables with initial research data.
Users add more niches through the dashboard Admin panel after this.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "nichescope.db")

INITIAL_KEYWORDS = {
    "beauty": [
        "nail stickers", "gel nail strips", "semi cured gel nails",
        "nail wraps", "nail art stickers", "false eyelashes",
        "cosmetic bags", "K-beauty nails", "3D nail art",
        "press on nails", "DIY manicure",
    ],
    "jewelry": [
        "septum rings", "nickel free jewelry", "hypoallergenic earrings",
        "body jewelry", "titanium jewelry", "surgical steel jewelry",
        "charms pendants", "chain belts", "nose rings",
        "nickel free earrings", "body piercing jewelry",
    ],
    "travel": [
        "packing cubes", "compression packing cubes", "travel pillow",
        "memory foam travel pillow", "luggage organizer",
        "hardshell suitcase", "canvas tote bag",
        "travel accessories", "carry on luggage",
    ],
    "home": [
        "home storage solutions", "dining room decor", "bookshelves",
        "ceiling decor", "pendant lights", "table centerpieces",
    ],
    "fashion": [
        "bodysuits", "skirts trending", "water sports clothing",
        "sleep shorts",
    ],
    "pets": [
        "dog plush toys", "dog bowls", "dog waste bags",
        "pet aquariums terrariums",
    ],
}

INITIAL_COMPETITORS = {
    "beauty": [
        {"name": "Glamnetic", "domain": "glamnetic.com", "platform": "shopify"},
        {"name": "Ohora", "domain": "ohora.com", "platform": "shopify"},
        {"name": "Dashing Diva", "domain": "dashingdiva.com", "platform": "shopify"},
    ],
    "jewelry": [
        {"name": "AMYO Jewelry", "domain": "amyojewelry.com", "platform": "shopify"},
        {"name": "Mejuri", "domain": "mejuri.com", "platform": "shopify"},
        {"name": "BodyCandy", "domain": "bodycandy.com", "platform": "custom"},
    ],
    "travel": [
        {"name": "BAGAIL", "domain": "bagail.com", "platform": "shopify"},
        {"name": "BAGSMART", "domain": "bagsmart.com", "platform": "shopify"},
        {"name": "Eagle Creek", "domain": "eaglecreek.com", "platform": "custom"},
    ],
}

INITIAL_SUPPLIERS = [
    {
        "name": "Shanghai Huizi Cosmetics",
        "region": "Shanghai",
        "product_focus": "Semi-cured gel nail strips, Korean-style designs",
        "price_range": "$0.62-2.25/unit",
        "moq": "500 pcs",
        "lead_time": "10-14 days",
        "quality_score": 8,
        "certifications": '["GMP"]',
        "contact_url": "https://huizi.en.alibaba.com",
        "notes": "Strong for branded gel strip lines. Korean aesthetic.",
    },
    {
        "name": "Guangzhou Yimei Printing",
        "region": "Guangzhou",
        "product_focus": "Nail stickers, tattoos, face gems. Full OEM.",
        "price_range": "$0.12-0.15/unit",
        "moq": "1000 pcs",
        "lead_time": "10-14 days",
        "quality_score": 9,
        "certifications": '["FSC","GMPC","ISO22716","SEDEX","Disney FAMA"]',
        "contact_url": "https://tiebeauty.en.alibaba.com",
        "notes": "Factory since 1999. Best compliance certs in the space.",
    },
    {
        "name": "Colorful Fashion Jewelry Co.",
        "region": "Yiwu",
        "product_focus": "Nickel-free fashion jewelry, charms, earrings, body jewelry",
        "price_range": "$0.10-1.50/pc",
        "moq": "12 pcs/style",
        "lead_time": "5-7 days",
        "quality_score": 8,
        "certifications": '["SGS","CPSIA","EU REACH"]',
        "contact_url": "https://www.clfjewelry.com",
        "notes": "17 yrs experience. Lead/nickel/cadmium-free certified. Low MOQ.",
    },
    {
        "name": "Yiwu J And D Jewelry",
        "region": "Yiwu",
        "product_focus": "Body jewelry, septum rings, nose studs",
        "price_range": "$0.30-2.00/pc",
        "moq": "100 pcs",
        "lead_time": "7-14 days",
        "quality_score": 8,
        "certifications": '["SGS"]',
        "contact_url": "",
        "notes": "39% reorder rate (highest in category). Good for bulk.",
    },
    {
        "name": "Dongguan Happy Beauty / Cool Jewelry",
        "region": "Dongguan",
        "product_focus": "Surgical steel jewelry, PVD plating, custom designs",
        "price_range": "$0.50-3.00/pc",
        "moq": "100 pcs",
        "lead_time": "15-25 days",
        "quality_score": 9,
        "certifications": '["ASTM F136"]',
        "contact_url": "",
        "notes": "2-3hr response time. Near-perfect reviews. Premium tier.",
    },
    {
        "name": "Dongguan I Am Flying Industry",
        "region": "Dongguan",
        "product_focus": "Travel pillows, memory foam, inflatable, hooded designs",
        "price_range": "$2.00-5.00/unit",
        "moq": "50 pcs",
        "lead_time": "15-20 days",
        "quality_score": 8,
        "certifications": '["CE","OEKO-TEX"]',
        "contact_url": "https://iamflying.en.alibaba.com",
        "notes": "Specialist travel pillow manufacturer. Custom logo OEM.",
    },
    {
        "name": "Quanzhou Maxtop Group",
        "region": "Quanzhou",
        "product_focus": "Compression packing cubes, luggage organizers, travel bags",
        "price_range": "$1.50-4.00/set",
        "moq": "100 sets",
        "lead_time": "18-25 days",
        "quality_score": 7,
        "certifications": "[]",
        "contact_url": "",
        "notes": "Large-scale travel accessories. Good for volume orders.",
    },
    {
        "name": "Guangzhou Zhengxiang Printing",
        "region": "Guangzhou",
        "product_focus": "Gel nail wraps, no-UV-lamp stickers, custom designs",
        "price_range": "$0.08-0.12/unit",
        "moq": "10 pcs",
        "lead_time": "7-14 days",
        "quality_score": 7,
        "certifications": "[]",
        "contact_url": "https://showyboo.en.alibaba.com",
        "notes": "Ultra low MOQ (10 pcs). Great for design testing.",
    },
]


def seed():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Seed keywords and auto-create categories
    keyword_count = 0
    for category, keywords in INITIAL_KEYWORDS.items():
        # Ensure category exists in categories table
        cursor.execute(
            "INSERT OR IGNORE INTO categories (name, sort_order) VALUES (?, ?)",
            (category, list(INITIAL_KEYWORDS.keys()).index(category)),
        )

        for kw in keywords:
            cursor.execute(
                "INSERT OR IGNORE INTO keywords (keyword, category) VALUES (?, ?)",
                (kw, category),
            )
            if cursor.rowcount > 0:
                keyword_count += 1
    print(f"Seeded {keyword_count} keywords across {len(INITIAL_KEYWORDS)} categories")

    # Seed competitors
    comp_count = 0
    for category, comps in INITIAL_COMPETITORS.items():
        for comp in comps:
            cursor.execute(
                "INSERT OR IGNORE INTO competitors (name, domain, category, platform) VALUES (?, ?, ?, ?)",
                (comp["name"], comp["domain"], category, comp["platform"]),
            )
            if cursor.rowcount > 0:
                comp_count += 1
    print(f"Seeded {comp_count} competitors")

    # Seed suppliers
    sup_count = 0
    for sup in INITIAL_SUPPLIERS:
        cursor.execute(
            """INSERT OR IGNORE INTO suppliers
               (name, region, product_focus, price_range, moq, lead_time,
                quality_score, certifications, contact_url, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sup["name"], sup["region"], sup["product_focus"],
                sup["price_range"], sup["moq"], sup["lead_time"],
                sup["quality_score"], sup["certifications"],
                sup["contact_url"], sup["notes"],
            ),
        )
        if cursor.rowcount > 0:
            sup_count += 1
    print(f"Seeded {sup_count} suppliers")

    conn.commit()
    conn.close()
    print("Seeding complete.")


if __name__ == "__main__":
    seed()
