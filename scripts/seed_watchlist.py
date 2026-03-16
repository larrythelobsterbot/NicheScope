#!/usr/bin/env python3
"""
Run once: python scripts/seed_watchlist.py
Populates keywords, competitors, suppliers, and categories tables with initial research data.
Users add more niches through the dashboard Admin panel after this.

Re-running is safe — uses INSERT OR IGNORE so existing data is not duplicated.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "nichescope.db")

# ============================================================
# KEYWORDS — grouped by category
# ============================================================
INITIAL_KEYWORDS = {
    # ── EXISTING ECOM CATEGORIES ─────────────────────────────
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

    # ── NEW ECOM CATEGORIES ──────────────────────────────────
    "wellness": [
        "sauna blanket", "infrared sauna blanket", "red light therapy device",
        "red light therapy mask", "light therapy lamp",
        "massage gun", "mouth tape sleep strips", "weighted sleep mask",
        "posture corrector", "ice bath tub portable", "sleep bonnet",
        "blue light blocking glasses", "acupressure mat",
    ],
    "eco_home": [
        "reusable silicone bags", "bamboo utensil set",
        "refillable cleaning bottles", "beeswax wraps",
        "compost bin kitchen", "glass straw set",
        "eco friendly sponge", "reusable paper towels",
        "silicone food covers", "biodegradable trash bags",
        "indoor herb garden kit",
    ],
    "smart_home": [
        "smart plug energy monitor", "LED strip lights",
        "smart water bottle", "desk cable management",
        "UV phone sanitizer", "portable monitor",
        "ergonomic laptop stand", "smart light bulb",
        "wireless charging pad", "noise machine sleep",
    ],
    "baby_kids": [
        "silicone baby feeder", "anti spill gyro bowl",
        "baby milestone blanket", "montessori toys",
        "kids sensory toys", "baby carrier wrap",
        "toddler tower", "baby teething toys",
        "muslin swaddle blanket", "baby nail trimmer electric",
    ],
    "fitness_gear": [
        "resistance band set", "yoga mat cork",
        "balance board", "foam roller",
        "hiking hydration pack", "travel yoga mat",
        "smart jump rope", "adjustable dumbbells",
        "pull up bar doorway", "massage ball set",
    ],
    "gaming_merch": [
        "retro gaming", "gaming desk setup",
        "custom mouse pad", "controller skin",
        "gaming room decor", "esports team merch",
        "LED gaming lights", "gaming headset stand",
        "cable management gaming", "pixel art display",
    ],
    "astrology_spiritual": [
        "tarot aesthetic", "zodiac jewelry",
        "crystal healing", "manifestation journal",
        "spiritual wall art", "birth chart poster",
        "chakra bracelet", "singing bowl meditation",
        "evil eye jewelry", "palo santo smudge kit",
    ],
    "book_culture": [
        "dark romance merch", "fantasy book aesthetic",
        "bookish gifts", "literary quote art",
        "book club gifts", "cozy reading accessories",
        "book sleeve", "reading journal",
        "bookshelf decor", "book lover candle",
    ],

    # ── ADSENSE / AFFILIATE CONTENT CATEGORIES ───────────────
    "personal_finance": [
        "best savings account", "credit card comparison",
        "budgeting app", "side hustle ideas",
        "passive income", "crypto wallet",
        "robo advisor", "debt payoff calculator",
        "high yield savings account", "investing for beginners",
    ],
    "insurance": [
        "car insurance quotes", "life insurance comparison",
        "pet insurance", "renters insurance",
        "travel insurance", "health insurance marketplace",
        "home insurance comparison", "disability insurance",
    ],
    "software_tools": [
        "AI writing tools", "best VPN service",
        "email marketing platform", "website builder comparison",
        "CRM software small business", "cloud hosting",
        "project management tools", "AI video generator",
        "password manager", "accounting software small business",
    ],
    "online_education": [
        "coding bootcamp", "online MBA programs",
        "data science certification", "graphic design course",
        "digital marketing course", "UX design bootcamp",
        "online degree programs", "language learning app",
    ],
}

# ============================================================
# COMPETITORS — ecom stores & content sites to track
# ============================================================
INITIAL_COMPETITORS = {
    # ── EXISTING ─────────────────────────────────────────────
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

    # ── NEW ECOM COMPETITORS ─────────────────────────────────
    "wellness": [
        {"name": "HigherDose", "domain": "higherdose.com", "platform": "shopify"},
        {"name": "Bon Charge", "domain": "boncharge.com", "platform": "shopify"},
        {"name": "Therabody", "domain": "therabody.com", "platform": "shopify"},
        {"name": "LifePro", "domain": "lifeprofitness.com", "platform": "shopify"},
    ],
    "eco_home": [
        {"name": "Bee's Wrap", "domain": "beeswrap.com", "platform": "shopify"},
        {"name": "Stasher", "domain": "stasherbag.com", "platform": "shopify"},
        {"name": "Blueland", "domain": "blueland.com", "platform": "shopify"},
        {"name": "Grove Collaborative", "domain": "grove.co", "platform": "custom"},
    ],
    "smart_home": [
        {"name": "Govee", "domain": "govee.com", "platform": "shopify"},
        {"name": "Oakywood", "domain": "oakywood.shop", "platform": "shopify"},
        {"name": "Twelve South", "domain": "twelvesouth.com", "platform": "shopify"},
    ],
    "baby_kids": [
        {"name": "Kyte Baby", "domain": "kytebaby.com", "platform": "shopify"},
        {"name": "Lovevery", "domain": "lovevery.com", "platform": "custom"},
        {"name": "Little Sleepies", "domain": "littlesleepies.com", "platform": "shopify"},
        {"name": "Posh Peanut", "domain": "poshpeanut.com", "platform": "shopify"},
    ],
    "fitness_gear": [
        {"name": "TheraBand", "domain": "therabandstore.com", "platform": "custom"},
        {"name": "Manduka", "domain": "manduka.com", "platform": "shopify"},
        {"name": "Crossrope", "domain": "crossrope.com", "platform": "shopify"},
        {"name": "REP Fitness", "domain": "repfitness.com", "platform": "shopify"},
    ],
    "gaming_merch": [
        {"name": "Glorious Gaming", "domain": "gloriousgaming.com", "platform": "shopify"},
        {"name": "NovelKeys", "domain": "novelkeys.com", "platform": "shopify"},
        {"name": "Displate", "domain": "displate.com", "platform": "custom"},
    ],
    "astrology_spiritual": [
        {"name": "Tiny Rituals", "domain": "tinyrituals.co", "platform": "shopify"},
        {"name": "Karma and Luck", "domain": "karmaandluck.com", "platform": "shopify"},
        {"name": "Energy Muse", "domain": "energymuse.com", "platform": "shopify"},
        {"name": "Moon Magic", "domain": "moonmagic.com", "platform": "shopify"},
    ],
    "book_culture": [
        {"name": "Litjoy Crate", "domain": "litjoycrate.com", "platform": "shopify"},
        {"name": "Out of Print", "domain": "outofprint.com", "platform": "shopify"},
        {"name": "Book of the Month", "domain": "bookofthemonth.com", "platform": "custom"},
    ],

    # ── ADSENSE / AFFILIATE CONTENT COMPETITORS ──────────────
    "personal_finance": [
        {"name": "NerdWallet", "domain": "nerdwallet.com", "platform": "custom"},
        {"name": "The Penny Hoarder", "domain": "thepennyhoarder.com", "platform": "wordpress"},
        {"name": "Bankrate", "domain": "bankrate.com", "platform": "custom"},
    ],
    "insurance": [
        {"name": "Policygenius", "domain": "policygenius.com", "platform": "custom"},
        {"name": "Insurify", "domain": "insurify.com", "platform": "custom"},
        {"name": "The Zebra", "domain": "thezebra.com", "platform": "custom"},
    ],
    "software_tools": [
        {"name": "G2", "domain": "g2.com", "platform": "custom"},
        {"name": "Capterra", "domain": "capterra.com", "platform": "custom"},
        {"name": "PCMag", "domain": "pcmag.com", "platform": "custom"},
    ],
    "online_education": [
        {"name": "Course Report", "domain": "coursereport.com", "platform": "custom"},
        {"name": "Class Central", "domain": "classcentral.com", "platform": "custom"},
        {"name": "Coursera", "domain": "coursera.org", "platform": "custom"},
    ],
}

# ============================================================
# SUPPLIERS — Alibaba / direct factories for physical products
# ============================================================
INITIAL_SUPPLIERS = [
    # ── EXISTING BEAUTY SUPPLIERS ────────────────────────────
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
    # ── EXISTING JEWELRY SUPPLIERS ───────────────────────────
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
    # ── EXISTING TRAVEL SUPPLIERS ────────────────────────────
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

    # ── NEW: WELLNESS SUPPLIERS ──────────────────────────────
    {
        "name": "Shenzhen Ideatherapy Technology",
        "region": "Shenzhen",
        "product_focus": "Red light therapy mats, infrared sauna blankets, LED therapy pads",
        "price_range": "$140-470/unit",
        "moq": "1 pc",
        "lead_time": "7-15 days",
        "quality_score": 8,
        "certifications": '["CE","FCC","FDA 510k"]',
        "contact_url": "https://ideatherapy.en.alibaba.com",
        "notes": "OEM/ODM. Quad-chip 660nm/850nm. Full body mats and blankets.",
    },
    {
        "name": "Guangzhou Maidi Electric Appliance",
        "region": "Guangzhou",
        "product_focus": "Infrared sauna blankets, heated body wraps, detox blankets",
        "price_range": "$42-120/unit",
        "moq": "1 pc",
        "lead_time": "7-14 days",
        "quality_score": 7,
        "certifications": '["CE","ROHS"]',
        "contact_url": "",
        "notes": "Budget-tier sauna blankets. Zipper design. Good entry-level sourcing.",
    },
    {
        "name": "Shenzhen Pinjian Technology",
        "region": "Shenzhen",
        "product_focus": "Massage guns, percussion therapy devices, mini massage guns",
        "price_range": "$15-45/unit",
        "moq": "10 pcs",
        "lead_time": "5-10 days",
        "quality_score": 8,
        "certifications": '["CE","FCC","ROHS"]',
        "contact_url": "",
        "notes": "Supplies private label massage guns. Quiet motor tech. Custom branding.",
    },

    # ── NEW: ECO HOME SUPPLIERS ──────────────────────────────
    {
        "name": "Shenzhen Kean Silicone Product Co.",
        "region": "Shenzhen",
        "product_focus": "Reusable silicone bags, food covers, kitchen storage",
        "price_range": "$0.80-2.50/unit",
        "moq": "100 pcs",
        "lead_time": "10-15 days",
        "quality_score": 8,
        "certifications": '["FDA","LFGB","BPA-Free"]',
        "contact_url": "",
        "notes": "Food-grade silicone specialist. Custom shapes and colors. OEM.",
    },
    {
        "name": "Fujian Weifu Bamboo & Wood Products",
        "region": "Fujian",
        "product_focus": "Bamboo utensil sets, bamboo straws, eco kitchen accessories",
        "price_range": "$0.50-3.00/set",
        "moq": "500 sets",
        "lead_time": "15-20 days",
        "quality_score": 7,
        "certifications": '["FSC","FDA"]',
        "contact_url": "",
        "notes": "Bamboo production base. Laser engraving for custom branding.",
    },
    {
        "name": "Dongguan Beeswax Product Factory",
        "region": "Dongguan",
        "product_focus": "Beeswax wraps, organic cotton wraps, eco food storage",
        "price_range": "$1.20-3.00/pack",
        "moq": "200 packs",
        "lead_time": "10-14 days",
        "quality_score": 7,
        "certifications": '["GOTS","FDA"]',
        "contact_url": "",
        "notes": "USDA organic beeswax sourcing. Assorted size packs. Custom prints.",
    },

    # ── NEW: SMART HOME SUPPLIERS ────────────────────────────
    {
        "name": "Shenzhen Gledopto Co.",
        "region": "Shenzhen",
        "product_focus": "Smart LED strips, smart bulbs, Zigbee/WiFi controllers",
        "price_range": "$3.00-15.00/unit",
        "moq": "50 pcs",
        "lead_time": "7-14 days",
        "quality_score": 8,
        "certifications": '["CE","FCC","ROHS"]',
        "contact_url": "",
        "notes": "Zigbee 3.0 compatible. Works with Alexa/Google. Custom branding.",
    },
    {
        "name": "Shenzhen Sikai Technology",
        "region": "Shenzhen",
        "product_focus": "Laptop stands, desk organizers, cable management accessories",
        "price_range": "$5.00-25.00/unit",
        "moq": "50 pcs",
        "lead_time": "7-15 days",
        "quality_score": 7,
        "certifications": '["CE","ROHS"]',
        "contact_url": "",
        "notes": "Aluminum and wood desk accessories. Ergonomic designs. OEM/ODM.",
    },

    # ── NEW: BABY/KIDS SUPPLIERS ─────────────────────────────
    {
        "name": "Dongguan ES-Pro Silicone Products",
        "region": "Dongguan",
        "product_focus": "Silicone baby teethers, montessori toys, baby feeders",
        "price_range": "$1.00-4.00/unit",
        "moq": "2 pcs",
        "lead_time": "5-10 days",
        "quality_score": 9,
        "certifications": '["FDA","BPA-Free","EN71","CPSIA"]',
        "contact_url": "",
        "notes": "100% food-grade silicone. Ultra low MOQ. Sensory toy specialist.",
    },
    {
        "name": "Yiwu Montessori Wood Toy Co.",
        "region": "Yiwu",
        "product_focus": "Wooden montessori toys, stacking toys, educational puzzles",
        "price_range": "$2.00-8.00/unit",
        "moq": "100 pcs",
        "lead_time": "10-20 days",
        "quality_score": 8,
        "certifications": '["EN71","ASTM","CE"]',
        "contact_url": "",
        "notes": "Natural wood finish. Non-toxic paints. Wide age range 0-6 years.",
    },
    {
        "name": "Hangzhou Baby Muslin Factory",
        "region": "Hangzhou",
        "product_focus": "Muslin swaddles, milestone blankets, baby wraps, bibs",
        "price_range": "$1.50-5.00/unit",
        "moq": "100 pcs",
        "lead_time": "10-15 days",
        "quality_score": 8,
        "certifications": '["OEKO-TEX","GOTS"]',
        "contact_url": "",
        "notes": "Organic cotton muslin. Custom printing. Bamboo muslin available.",
    },

    # ── NEW: FITNESS GEAR SUPPLIERS ──────────────────────────
    {
        "name": "Hebei Dingyan Trading Co.",
        "region": "Hebei",
        "product_focus": "Resistance bands (latex/fabric), pull-up bands, exercise bands",
        "price_range": "$0.50-6.00/set",
        "moq": "100 sets",
        "lead_time": "7-14 days",
        "quality_score": 8,
        "certifications": '["SGS","REACH"]',
        "contact_url": "",
        "notes": "OEM fabric and latex bands. Custom logo printing. Color sets.",
    },
    {
        "name": "Fujian Cork Yoga Mat Factory",
        "region": "Fujian",
        "product_focus": "Cork yoga mats, TPE yoga mats, travel yoga mats",
        "price_range": "$6.00-18.00/unit",
        "moq": "50 pcs",
        "lead_time": "15-25 days",
        "quality_score": 8,
        "certifications": '["SGS","OEKO-TEX","CE"]',
        "contact_url": "",
        "notes": "Natural cork surface. Custom full-color printing. Eco-friendly TPE base.",
    },
    {
        "name": "Nantong Foam Product Co.",
        "region": "Nantong",
        "product_focus": "Foam rollers, massage balls, balance boards, yoga blocks",
        "price_range": "$2.00-10.00/unit",
        "moq": "200 pcs",
        "lead_time": "10-20 days",
        "quality_score": 7,
        "certifications": '["SGS"]',
        "contact_url": "",
        "notes": "EVA and EPP foam specialist. Custom density and texture options.",
    },

    # ── NEW: ASTROLOGY / SPIRITUAL SUPPLIERS ─────────────────
    {
        "name": "Yiwu Spiritual Crystal Trading",
        "region": "Yiwu",
        "product_focus": "Healing crystals, crystal bracelets, chakra stones, pendulums",
        "price_range": "$0.30-5.00/pc",
        "moq": "50 pcs",
        "lead_time": "3-7 days",
        "quality_score": 7,
        "certifications": "[]",
        "contact_url": "",
        "notes": "Wide variety of natural stones. Fast shipping from Yiwu. Low MOQ.",
    },
    {
        "name": "Guangzhou Tarot & Printing Co.",
        "region": "Guangzhou",
        "product_focus": "Custom tarot decks, oracle cards, zodiac art prints",
        "price_range": "$2.00-8.00/deck",
        "moq": "100 decks",
        "lead_time": "10-18 days",
        "quality_score": 8,
        "certifications": '["FSC"]',
        "contact_url": "",
        "notes": "Full custom card printing. Gold foil, holographic options. Tuck boxes.",
    },

    # ── NEW: GAMING MERCH SUPPLIERS ──────────────────────────
    {
        "name": "Shenzhen RGB Peripherals Co.",
        "region": "Shenzhen",
        "product_focus": "Custom mouse pads (desk-size), LED gaming lights, headset stands",
        "price_range": "$2.00-12.00/unit",
        "moq": "50 pcs",
        "lead_time": "7-14 days",
        "quality_score": 7,
        "certifications": '["CE","ROHS"]',
        "contact_url": "",
        "notes": "Full-surface custom printing on XL mouse pads. RGB LED accent lighting.",
    },

    # ── NEW: BOOK CULTURE SUPPLIERS ──────────────────────────
    {
        "name": "Wenzhou Padded Sleeve Factory",
        "region": "Wenzhou",
        "product_focus": "Book sleeves, padded tablet cases, zippered pouches",
        "price_range": "$1.50-4.00/unit",
        "moq": "200 pcs",
        "lead_time": "10-15 days",
        "quality_score": 7,
        "certifications": "[]",
        "contact_url": "",
        "notes": "Custom fabric printing. Padded book sleeves popular on Etsy/TikTok.",
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
