"""
keyword_filter.py — NicheScope shared junk-keyword detector
============================================================
Single public API:

    is_junk(keyword: str) -> tuple[bool, str]

Returns (True, reason_string) if the keyword should be blocked before it
enters pending_keywords, or (False, "") if it looks legitimate.

Design goals
------------
* HIGH PRECISION — avoid false positives.  A missed junk keyword is
  acceptable; a blocked valid keyword (e.g. "birthday freebies",
  "maybelline instant age rewind", "vitamina c para o rosto") is not.
* All pattern lists are module-level constants so they're easy to tune
  without touching the logic.
* Logs at DEBUG level so the caller can see what was filtered and why.
"""

import re
import logging
import unicodedata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule 1 — Entertainment / streaming patterns
# ---------------------------------------------------------------------------
_ENTERTAINMENT_PATTERNS: list[re.Pattern] = [
    re.compile(r'\bwhere to watch\b', re.I),
    re.compile(r'\bbased on (a |the )?true story\b', re.I),
    re.compile(r'\bis .{1,60} true story\b', re.I),
    re.compile(r'\bseason \d+\b', re.I),
    re.compile(r'\bepisode \d+\b', re.I),
    re.compile(r'\bnetflix original\b', re.I),
    re.compile(r'\bon hulu\b', re.I),
    re.compile(r'\bon disney\b', re.I),  # "on disney+" / "on disney plus"
    re.compile(r'\bimdb rating\b', re.I),
    re.compile(r'\blyrics\b', re.I),
    re.compile(r'\bsaturday night live\b', re.I),
    re.compile(r'\bsnl host\b', re.I),
    re.compile(r'\bsnl cast\b', re.I),
    # "true story" as a standalone phrase (catches "marty supreme true story")
    # Note: "is X a true story" / "based on true story" already caught above;
    # this catches bare "X true story" endings.
    re.compile(r'\btrue story\b', re.I),
    # Cinema / episode / fansub queries (July 2026 bulk-import trash wave)
    re.compile(r'\bshowtimes?\b', re.I),
    re.compile(r'\bbox office\b', re.I),
    re.compile(r'\beng(?:lish)? subs?\b', re.I),
    re.compile(r'\bep \d+\b', re.I),           # "ep 10 eng sub" ("episode N" already covered)
    re.compile(r'\b(bilibili|dailymotion|dramacool)\b', re.I),
    re.compile(r'\bstreaming$', re.I),          # "<title> streaming"; protects "streaming microphone"
    re.compile(r'\b(png|wallpapers?)$', re.I),  # fandom asset hunts
    re.compile(r'\btranslation$', re.I),        # "<lyrics> latin translation"
]

# ---------------------------------------------------------------------------
# Rule 2 — News / politics / disaster events
# ---------------------------------------------------------------------------
# "shooting" is blocked ONLY as a standalone word or in clear news contexts;
# "shooting star", "shooting for", etc. are protected by the word boundary
# plus the explicit news phrases.
_NEWS_PATTERNS: list[re.Pattern] = [
    re.compile(r'\btrump news\b', re.I),
    re.compile(r'\bbiden news\b', re.I),
    re.compile(r'\belection results\b', re.I),
    re.compile(r'\bsports news today\b', re.I),
    re.compile(r'\bearthquake\b', re.I),
    re.compile(r'\bhurricane\b', re.I),
    # "shooting" only when it reads as a crime/incident report:
    # matches "shooting in …", "mass shooting", "police shooting" but NOT
    # "shooting star", "trouble shooting", "photo shooting"
    re.compile(r'\b(mass|police|active|deadly|school|church|nightclub) shooting\b', re.I),
    re.compile(r'\bshooting (?:in|near|at|suspect|victim|death|kills)\b', re.I),
    # Generic news queries — almost never a product. Catches "<x> news",
    # "news <x>", "breaking/latest/international news", "<x> news today".
    # A product keyword essentially never ends in "news", so this is safe.
    re.compile(r'\bnews\b\s*(today|update|latest)?\s*$', re.I),
    re.compile(r'^\s*(breaking|latest|international|today\b.*)\s+news\b', re.I),
    re.compile(r'\bnews\s+(today|update|on|of|about)\b', re.I),
    # AI / tech-company / market news feeds that slipped into commerce cats
    re.compile(r'\b(openai|anthropic|nvidia|github|shopify|stripe|gumroad|'
               r'crypto|bitcoin|ethereum|stock market|federal reserve|'
               r'mortgage rates?|gold price|oil price)\b.*\bnews\b', re.I),
    re.compile(r'\b(ai|artificial intelligence|crypto|tech|semiconductor)\s+news\b', re.I),
    # Commodity price-checking (not product searches): "mcx gold silver prices",
    # "gold and silver price today india". Protects products like "14k gold
    # necklace" because it requires the price/rate token.
    re.compile(r'\b(gold|silver|platinum|crude|petrol|diesel)\b[^,]*\b(price|prices|rate|rates)\b', re.I),
    re.compile(r'\bmcx\b', re.I),
    # Event/sports spectacles (plural "olympics" protects "olympic barbell")
    re.compile(r'\bolympics\b', re.I),
    re.compile(r'\bworld cup\b', re.I),
    # Finance/admin process queries
    re.compile(r'\bkyc\b', re.I),
]

# ---------------------------------------------------------------------------
# Rule 3 — Sports scores / standings / team-specific
# ---------------------------------------------------------------------------
_SPORTS_PATTERNS: list[re.Pattern] = [
    re.compile(
        r'\b(blue jays|raptors|maple leafs|knicks|lakers|warriors|celtics'
        r'|heat (?:vs|score|game))\b', re.I
    ),
    re.compile(r'\bnfl (?:draft|standings|score|scores)\b', re.I),
    re.compile(r'\bnba (?:standings|draft|trade|score|scores)\b', re.I),
]

# ---------------------------------------------------------------------------
# Rule 4 — Non-English non-beauty
# Beauty / product indicator words that make a non-ASCII keyword valid.
# Keep this list conservative — a missed beauty term is fine; a blocked
# valid keyword (e.g. "vitamina c para o rosto") is not.
# ---------------------------------------------------------------------------
_BEAUTY_INDICATOR_WORDS: frozenset[str] = frozenset([
    "serum", "cream", "toner", "mask", "cleanser", "sunscreen",
    "moisturizer", "vitamin", "vitamina",   # Portuguese "vitamina"
    "spf", "uv", "skincare", "makeup", "cosmetic", "perfume", "fragrance",
    "nail", "hair", "lip", "eye", "face", "skin", "gel", "oil", "lotion",
    "essence", "ampoule", "mist", "balm", "exfoliant", "exfoliator",
    "primer", "foundation", "blush", "concealer", "contour", "highlight",
    "mascara", "eyeliner", "brow", "lash", "gloss", "liner", "rouge",
    "retinol", "niacinamide", "hyaluronic", "collagen", "peptide",
    "brightening", "whitening", "hydrating", "anti-aging", "antiaging",
    "hairspray", "setting", "powder", "lipstick", "bronzer", "highlighter",
    "eyeshadow", "eyebrow", "eyelash", "blush", "sunblock",
    "pdrn", "aha", "bha", "pha", "acid", "spf", "tretinoin",
    "salicylic", "glycolic", "centella", "niacinamide", "mugwort", "bakuchiol",
    "spray", "mist", "essence", "serum",  # ensure common formats covered
    "rosto",        # Portuguese "face"
    "pele",         # Portuguese "skin"
    "creme",        # French/Portuguese "cream"
    "crema",        # Spanish "cream"
    "soro",         # Portuguese "serum"
    "hidratante",   # Portuguese/Spanish "moisturizer"
    "protetor",     # Portuguese "sunscreen/protector"
    "protector",
    "solaire",      # French "sunscreen"
    "visage",       # French "face"
    "peaux",        # French "skin (plural)"
    "peau",         # French "skin"
    "corps",        # French "body"
    "cheveux",      # French "hair"
    "beaute", "beauté",
    "skincare", "bodycare", "haircare",
])

# Product indicator words for non-beauty categories. A non-Latin-script
# keyword containing any of these (e.g. a mixed-script query like
# "ohora ネイル strips") is a product search, not junk. Without this list
# the non-Latin rule structurally blocked every non-English keyword
# outside beauty. Kept conservative: generic product nouns only.
_PRODUCT_INDICATOR_WORDS: frozenset[str] = frozenset([
    # jewelry
    "ring", "rings", "necklace", "bracelet", "earrings", "earring",
    "pendant", "charm", "anklet", "piercing", "jewelry", "jewellery",
    # home / kitchen
    "organizer", "organiser", "shelf", "lamp", "rug", "curtain", "pillow",
    "blanket", "mattress", "decor", "vase", "candle", "humidifier",
    # fitness / wellness
    "yoga", "pilates", "dumbbell", "resistance", "protein", "supplement",
    "massager", "fitness", "workout",
    # baby / kids
    "stroller", "crib", "diaper", "pacifier", "teether", "montessori",
    # pets
    "leash", "collar", "aquarium", "terrarium", "litter",
    # travel / bags
    "luggage", "suitcase", "backpack", "tote", "pouch", "wallet",
    # tech accessories
    "charger", "case", "stand", "holder", "tripod", "earbuds", "headphones",
    # generic commerce
    "kit", "set", "strips", "sticker", "stickers", "wrap", "wraps",
    "organic", "portable", "wireless", "mini", "refill",
])

_ALL_PRODUCT_INDICATORS: frozenset[str] = _BEAUTY_INDICATOR_WORDS | _PRODUCT_INDICATOR_WORDS


def _has_non_latin_script(text: str) -> bool:
    """
    Return True only if *text* contains characters from non-Latin scripts
    (CJK, Arabic, Cyrillic, Hebrew, Devanagari, etc.).

    Accented Latin characters like é, ñ, ü, ó are fine — they appear in
    legitimate brand names like TRESemmé, L'Oréal, or international queries
    like 'vitamina c para o rosto'. Only truly foreign-script characters
    trigger this rule.
    """
    for ch in text:
        if ord(ch) <= 127:
            continue  # plain ASCII — fine
        cat = unicodedata.category(ch)
        if cat.startswith('M'):
            continue  # combining diacritical marks (accent modifiers) — fine
        name = unicodedata.name(ch, '')
        if 'LATIN' in name:
            continue  # Latin Extended-A/B/C/D — accented brand chars — fine
        if cat in ('Zs', 'Po', 'Pd', 'Ps', 'Pe'):
            continue  # special spaces, punctuation — fine
        # Anything else (CJK, Arabic, Cyrillic, Hiragana, Katakana, etc.)
        return True
    return False


def _contains_product_indicator(text_lower: str) -> bool:
    """Return True if any product indicator word appears as a word token."""
    # Split on spaces and common punctuation so "vitamina" matches in
    # "vitamina c para o rosto".
    tokens = re.split(r'[\s\-/&\(\)]+', text_lower)
    return bool(frozenset(tokens) & _ALL_PRODUCT_INDICATORS)


# ---------------------------------------------------------------------------
# Rule 5 — Celebrity trivia / personal trivia with no product angle
#
# Pattern forms blocked:
#   "<name> true story"                  (is X a true story)
#   "<name> sexuality / ethnicity / ..."
#   "X Y birthday / age / height / net worth"  (three-word name-like phrase)
#
# Guard: if the keyword contains a beauty brand indicator, we let it through.
# ---------------------------------------------------------------------------
_CELEBRITY_PATTERNS: list[re.Pattern] = [
    # "is [name] a true story" / "is [movie title] true story"
    re.compile(r'\bis .{5,40}(?: a)? true story\b', re.I),
    # "[was|is] [name] [attribute]" — personal trivia questions
    re.compile(
        r'\b(is|was) .{3,30}\b'
        r'(?:sexuality|ethnicity|religion|nationality|real name|net worth)\b',
        re.I
    ),
    # Three-word+ phrases ending in personal trivia nouns.
    # E.g. "john doe birthday", "taylor swift age", "kim kardashian height"
    # Uses a lookahead to ensure there are at least two prior word tokens.
    re.compile(
        r'(?:\w+\s+){1,4}\w+\s+(?:birthday|height|net worth|nationality|ethnicity|religion|sexuality)\b',
        re.I
    ),
]

# Beauty brand / product signal words — if present the celebrity rule is waived
_BRAND_SIGNALS: frozenset[str] = frozenset([
    "cream", "serum", "toner", "mask", "cleanser", "sunscreen", "moisturizer",
    "vitamin", "vitamina", "spf", "uv", "skincare", "makeup", "cosmetic",
    "perfume", "fragrance", "nail", "gel", "oil", "lotion", "balm",
    "retinol", "niacinamide", "hyaluronic", "collagen", "peptide",
    "foundation", "concealer", "mascara", "primer", "blush", "lipstick",
    "gloss", "liner", "palette", "brush", "sponge", "applicator",
    "ingredients", "review", "dupe", "alternative", "vs", "comparison",
    "routine", "tutorial", "haul", "unboxing",
    # Retail/commercial intent signals — waive birthday/celebrity rule for
    # searches like "sephora free birthday gift", "birthday freebies 2026"
    "gift", "freebie", "freebies", "deal", "discount", "sale", "promo",
    "coupon", "free", "giveaway",
])


def _has_brand_signal(text_lower: str) -> bool:
    tokens = re.split(r'[\s\-/&\(\)]+', text_lower)
    return bool(frozenset(tokens) & _BRAND_SIGNALS)


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

# Bare utility/navigation queries with zero product intent — exact match only,
# so they can never clip a longer legitimate keyword.
_EXACT_JUNK: frozenset[str] = frozenset([
    "maps", "weather", "calculator", "translate", "news", "nail salon",
    "google", "youtube", "amazon",
])


def is_junk(keyword: str) -> tuple[bool, str]:
    """
    Decide whether *keyword* is junk that should be blocked.

    Returns
    -------
    (True, reason)  — block the keyword
    (False, "")     — keyword looks legitimate, let it through
    """
    if not keyword or not keyword.strip():
        return True, "empty keyword"

    kw_lower = keyword.strip().lower()

    # --- Rule 0: bare utility queries, exact match ---
    if kw_lower in _EXACT_JUNK:
        return True, "bare utility/navigation query"

    # --- Rule 1: Entertainment / streaming ---
    for pat in _ENTERTAINMENT_PATTERNS:
        if pat.search(kw_lower):
            # For the bare "true story" pattern, waive if a product signal is
            # present — e.g. a hypothetical "true story behind retinol" article.
            if r'true story' in pat.pattern and _has_brand_signal(kw_lower):
                continue
            reason = f"entertainment/streaming: matched /{pat.pattern}/"
            logger.debug("is_junk blocked %r — %s", keyword, reason)
            return True, reason

    # --- Rule 2: News / politics / disasters ---
    for pat in _NEWS_PATTERNS:
        if pat.search(kw_lower):
            reason = f"news/politics: matched /{pat.pattern}/"
            logger.debug("is_junk blocked %r — %s", keyword, reason)
            return True, reason

    # --- Rule 3: Sports scores / teams ---
    for pat in _SPORTS_PATTERNS:
        if pat.search(kw_lower):
            reason = f"sports: matched /{pat.pattern}/"
            logger.debug("is_junk blocked %r — %s", keyword, reason)
            return True, reason

    # --- Rule 4: Non-Latin-script with no product indicator ---
    if _has_non_latin_script(kw_lower):
        if not _contains_product_indicator(kw_lower):
            reason = "non-ASCII characters with no product indicator word"
            logger.debug("is_junk blocked %r — %s", keyword, reason)
            return True, reason

    # --- Rule 5: Celebrity / personal trivia (no product angle) ---
    for pat in _CELEBRITY_PATTERNS:
        if pat.search(kw_lower):
            # Waive the rule if there's a brand/product signal present
            if _has_brand_signal(kw_lower):
                logger.debug(
                    "is_junk: celebrity pattern matched for %r but brand signal present — allowing",
                    keyword,
                )
                break
            reason = f"celebrity trivia: matched /{pat.pattern}/"
            logger.debug("is_junk blocked %r — %s", keyword, reason)
            return True, reason

    return False, ""
