"""
farmer_assistant.py
--------------------
Lets a farmer type a free-text question in English OR Urdu (e.g. "what is
the price of wheat" or "گندم کی قیمت کیا ہے") and get an answer about a
specific crop's current price, trend, and forecast — answered back in
whichever language the question was asked in.

PIPELINE:
1. Detect the query's language (Urdu vs English) — done locally, no API
   call needed, since Urdu uses a distinct Unicode range.
2. If Urdu, translate the query to English using Gemini (needed because the
   crop-matching step below compares against English crop names).
3. Fuzzy-match the translated query against the known crop names in the
   dataset, using Python's built-in difflib — no extra dependency, and good
   enough for matching short crop names/phrases.
4. Detect a city/mandi name from the question (if the farmer named one).
   Falls back to Dashboard-selected regions, then any region with data.
5. Optionally parse a single date ("on 15 March") or range
   ("from 1 March to 15 March") from the question.
6. Pull stats: latest price (default), price on a date, or min/avg/max
   over a range — using the same data as the dashboard.
7. Build a plain-English answer sentence from those stats.
8. If the original question was in Urdu, translate the answer back to Urdu
   using Gemini before returning it.

WHY GEMINI FOR TRANSLATION INSTEAD OF A TRANSLATION LIBRARY?
Keeps the dependency list small (already using Gemini for AI insights) and
Gemini handles agricultural terms in Urdu reasonably well. The tradeoff:
translation requires an API key and a network call, so this feature quietly
degrades to "crop not understood" if no key is configured — it does not
crash the app.
"""

import re
import json
import difflib
from datetime import datetime, timedelta
from price_utils import find_valid_region, get_crop_stats, get_forecast, rule_based_advice
from ai_advisory import call_gemini_raw

# ROMAN URDU SUPPORT: most Pakistani farmers text in Urdu written with
# English letters ("aloo ki keemat kya hai"), not actual Urdu script. The
# original language detector only caught real Urdu script (Unicode
# U+0600-U+06FF), so Roman Urdu queries were silently treated as English —
# which meant "aloo" never matched "Potato" and the answer never got
# translated back. These two lookups fix that:
# 1. Common crop names in Roman Urdu -> their English equivalent, so
#    matching works even though the words look nothing alike.
# 2. Common Roman Urdu grammar words ("hai", "kya", "kitni", "keemat") -
#    if a query contains these, treat it as Urdu for response purposes even
#    though it's written in Latin letters and the script-check missed it.
ROMAN_URDU_CROP_SYNONYMS = {
    "aloo": "potato", "alu": "potato",
    "pyaz": "onion", "pyaaz": "onion", "piyaz": "onion",
    "tamatar": "tomato", "tamater": "tomato",
    "gandum": "wheat", "ganeh": "wheat",
    "chawal": "rice", "chaawal": "rice",
    "gobi": "cauliflower",
    "matar": "peas",
    "adrak": "ginger",
    "lehsan": "garlic", "lehsun": "garlic",
    "seb": "apple",
    "kela": "banana", "kelaa": "banana",
    "santra": "orange", "musammi": "orange",
    "amrud": "guava",
    "angoor": "grape",
    "kharbooza": "melon",
    "tarbooz": "watermelon",
    "palak": "spinach",
    "gajar": "carrot",
    "mirch": "chili", "mirchi": "chili",
    "makai": "maize", "makkai": "corn",
    "jau": "barley",
    "masoor": "lentil",
    "chana": "chickpea", "channa": "chickpea",
    "shakarqandi": "sweet potato",
    "bhindi": "okra",
    "baingan": "brinjal", "baingann": "eggplant",
    "karela": "bittergourd",
    "lauki": "gourd",
    "kaddu": "pumpkin",
}

ROMAN_URDU_MARKER_WORDS = {
    "kia", "kya", "hai", "hain", "ka", "ki", "ke", "mein", "kitni", "kitna",
    "keemat", "qeemat", "daam", "bhao", "kab", "kahan", "kaisa", "kaisi", "bataye",
}


def detect_language(text):
    """
    Returns 'ur' if the text is Urdu — either real Urdu script (Unicode
    U+0600-U+06FF) or Roman Urdu (Latin letters but Urdu grammar/vocabulary,
    detected via common marker words or crop-name synonyms above).
    Otherwise returns 'en'.
    """
    for ch in text:
        if "\u0600" <= ch <= "\u06FF":
            return "ur"

    words = re.findall(r"\w+", text.lower())
    if any(w in ROMAN_URDU_MARKER_WORDS or w in ROMAN_URDU_CROP_SYNONYMS for w in words):
        return "ur"

    return "en"


def expand_roman_urdu_crop_names(text):
    """
    Appends the English equivalent of any recognized Roman Urdu crop name
    onto the text, so match_crop() has an actual English word to work with.
    E.g. "aloo price" becomes "aloo price potato" — match_crop then finds
    "potato" in there and matches correctly.
    """
    words = re.findall(r"\w+", text.lower())
    additions = [ROMAN_URDU_CROP_SYNONYMS[w] for w in words if w in ROMAN_URDU_CROP_SYNONYMS]
    return text + " " + " ".join(additions) if additions else text


def translate_text(text, target_lang):
    """Translates text to English or Urdu using Gemini. Returns None if the
    call fails (no key, network issue, etc.) — callers must handle that."""
    target_name = "English" if target_lang == "en" else "Urdu"
    prompt = (
        f"Translate the following text to {target_name}. "
        f"Output ONLY the translation, nothing else, no explanation:\n\n{text}"
    )
    return call_gemini_raw(prompt)


def load_crop_translations():
    """
    Loads crop_translations.json (built by build_crop_translations.py), if
    it exists. Returns {} if not — matching still works using plain English
    words and the small hardcoded Roman Urdu dictionary above, just without
    the fuller crop-specific Urdu/Roman Urdu vocabulary.
    """
    try:
        with open("crop_translations.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _crop_candidate_words(crop, translations):
    """
    All words that should count as referring to this crop: its English
    name, ALL its known Roman Urdu spelling variants (since phonetic
    transliteration allows several valid spellings for the same word —
    e.g. "seb" and "saib" are both correct for سیب/apple), and its Urdu
    script name.
    """
    words = set(re.findall(r"\w+", crop.lower()))
    entry = translations.get(crop)
    if entry:
        roman_variants = entry.get("roman_urdu", [])
        if isinstance(roman_variants, str):
            roman_variants = [roman_variants]  # backward-compat with older single-string format
        for variant in roman_variants:
            words.update(re.findall(r"\w+", variant.lower()))
        if entry.get("urdu"):
            # Urdu script has no upper/lowercase, so words are compared
            # as-is rather than lowercased like the English/Roman ones.
            words.update(entry["urdu"].split())
    return words


CONFIDENT_MATCH_SCORE = 2  # at least one exact word match, or two weaker fuzzy ones


def score_crops(query_words, known_crops, translations):
    """
    Scores every known crop against the query's words (already lowercased/
    tokenized by the caller). Returns a list of (crop, score) sorted
    highest-first — the caller decides what counts as "confident enough"
    versus merely "worth suggesting."
    """
    scored = []
    for crop in known_crops:
        candidates = _crop_candidate_words(crop, translations)
        score = 0
        for cand in candidates:
            if cand in query_words:
                score += 2  # exact word match — strong signal
            else:
                close = difflib.get_close_matches(cand, query_words, n=1, cutoff=0.7)
                if close:
                    score += 1  # fuzzy/partial match — weaker signal
        if score > 0:
            scored.append((crop, score))

    scored.sort(key=lambda x: -x[1])
    return scored


def match_crop(query_en, known_crops, translations=None):
    """
    Returns (matched_crop, suggested_crop). Exactly one of these is set (or
    both None if nothing at all matched):
      - matched_crop: a confident match — proceed normally
      - suggested_crop: a weak/partial match — not confident enough to
        answer directly, but worth asking "did you mean X?" instead of a
        flat "couldn't find it" failure.
    """
    if translations is None:
        translations = {}

    # Match against BOTH the (possibly translated-to-English) query words
    # AND the original raw query's words — covers cases where the original
    # Urdu-script or Roman Urdu text matches a stored translation directly,
    # even if the English translation round-trip lost some precision.
    query_words = re.findall(r"\w+", query_en.lower())
    if not query_words:
        return None, None

    scored = score_crops(query_words, known_crops, translations)
    if not scored:
        return None, None

    top_crop, top_score = scored[0]
    if top_score >= CONFIDENT_MATCH_SCORE:
        return top_crop, None
    else:
        return None, top_crop  # weak match — offer as a suggestion, not a direct answer


def _normalize_place(name):
    """Lowercase and strip spaces/punctuation so 'Bahawal Pur', 'Bahawalpur',
    and 'BahawalPur' all become 'bahawalpur' for comparison."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def match_region(query_text, known_regions):
    """
    Tries to detect a city/mandi name from the farmer's question.
    Returns the best matching region string (exact spelling from the dataset),
    or None if nothing clear is found.

    Your dataset uses concatenated names (BahawalPur, AhmadPurEast, DGKHAN).
    Farmers usually type spaced or common spellings (Bahawalpur, D.G. Khan).
    Matching strategy (strongest first):
      1. Normalized exact match (ignore spaces/case/punctuation)
      2. Query word(s) are a prefix/substring of a region (or vice-versa),
         preferring the longest region name to avoid false positives
      3. Fuzzy match via difflib for minor typos
    """
    if not known_regions:
        return None

    query_lower = query_text.lower()
    query_norm = _normalize_place(query_text)
    query_words = re.findall(r"[a-z0-9]+", query_lower)

    # Pre-compute normalized forms once
    region_norms = {region: _normalize_place(region) for region in known_regions}

    # 1. Normalized exact match: "bahawalpur" == "BahawalPur"
    for region, r_norm in region_norms.items():
        if len(r_norm) >= 4 and r_norm in query_norm:
            return region
        # Also: multi-word query like "bahawal pur" already normalized above

    # 2. Any query word (length >= 4) that is a substantial substring of a
    #    region name, or a region name that is a substring of a query word.
    #    Prefer longer region matches to avoid "pur" matching half the list.
    candidates = []
    for region, r_norm in region_norms.items():
        if len(r_norm) < 4:
            continue
        for w in query_words:
            if len(w) < 4:
                continue
            if w in r_norm or r_norm in w:
                # score by how much of the region name was covered
                overlap = min(len(w), len(r_norm))
                candidates.append((overlap, len(r_norm), region))
    if candidates:
        candidates.sort(key=lambda x: (-x[0], -x[1]))
        return candidates[0][2]

    # 3. Fuzzy match against full normalized region names
    norm_list = list(region_norms.values())
    # Try each reasonably long query token + the full normalized query
    probes = [w for w in query_words if len(w) >= 5] + ([query_norm] if len(query_norm) >= 5 else [])
    best_region, best_score = None, 0.0
    for probe in probes:
        close = difflib.get_close_matches(probe, norm_list, n=1, cutoff=0.82)
        if close:
            score = difflib.SequenceMatcher(None, probe, close[0]).ratio()
            if score > best_score:
                best_score = score
                # map normalized form back to original region string
                for region, r_norm in region_norms.items():
                    if r_norm == close[0]:
                        best_region = region
                        break
    if best_region:
        return best_region

    return None


# ---------------------------------------------------------------------------
# DATE PARSING (Option A: single date "on X" or range "from X to Y")
# ---------------------------------------------------------------------------
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_DATE_FORMATS = (
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
    "%d-%m-%y", "%d/%m/%y", "%d %m %Y", "%d %m %y",
)


def _parse_one_date(text, default_year=None):
    """Try to parse a single date string. Returns datetime.date or None."""
    text = text.strip().strip(",.")
    if not text:
        return None

    # Numeric formats first
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    # "15 March", "15 March 2025", "March 15", "March 15 2025"
    m = re.match(
        r"^(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(\d{4}))?$",
        text, re.I,
    )
    if m:
        day, mon, year = int(m.group(1)), m.group(2).lower()[:3], m.group(3)
        month = _MONTHS.get(mon) or _MONTHS.get(m.group(2).lower())
        if month and 1 <= day <= 31:
            y = int(year) if year else (default_year or datetime.now().year)
            try:
                return datetime(y, month, day).date()
            except ValueError:
                return None

    m = re.match(
        r"^([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?$",
        text, re.I,
    )
    if m:
        mon, day, year = m.group(1).lower()[:3], int(m.group(2)), m.group(3)
        month = _MONTHS.get(mon) or _MONTHS.get(m.group(1).lower())
        if month and 1 <= day <= 31:
            y = int(year) if year else (default_year or datetime.now().year)
            try:
                return datetime(y, month, day).date()
            except ValueError:
                return None

    return None


def parse_dates_from_query(query_text):
    """
    Detect a single date or a date range in the question.
    Returns one of:
      ("on", date)           — e.g. "on 15 March", "on 2025-03-15"
      ("range", start, end)  — e.g. "from 1 March to 15 March"
      (None, None)           — no date found
    """
    q = query_text.strip()
    default_year = datetime.now().year

    # Range patterns: from X to Y / between X and Y / X to Y / X - Y
    range_patterns = [
        r"(?:from|between)\s+(.+?)\s+(?:to|and|-|–|—)\s+(.+?)(?:\s|$|\.|\?)",
        r"(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})\s*(?:to|-|–|—)\s*(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})",
        r"(\d{1,2}\s+[A-Za-z]+(?:\s+\d{4})?)\s*(?:to|-|–|—)\s*(\d{1,2}\s+[A-Za-z]+(?:\s+\d{4})?)",
        r"([A-Za-z]+\s+\d{1,2}(?:\s+\d{4})?)\s*(?:to|-|–|—)\s*([A-Za-z]+\s+\d{1,2}(?:\s+\d{4})?)",
    ]
    for pat in range_patterns:
        m = re.search(pat, q, re.I)
        if m:
            start = _parse_one_date(m.group(1), default_year)
            end = _parse_one_date(m.group(2), default_year)
            if start and end:
                if start > end:
                    start, end = end, start
                return ("range", start, end)

    # Single date: "on DATE" or standalone clear date
    on_patterns = [
        r"\bon\s+(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})",
        r"\bon\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+(?:\s+\d{4})?)",
        r"\bon\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?)",
        r"\bdated?\s+(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})",
    ]
    for pat in on_patterns:
        m = re.search(pat, q, re.I)
        if m:
            d = _parse_one_date(m.group(1), default_year)
            if d:
                return ("on", d, None)

    return (None, None, None)


def _price_on_date(df, crop, region, target_date):
    """
    Price on target_date, or nearest available day within ±7 days.
    Returns (price, actual_date) or (None, None).
    """
    import pandas as pd

    sub = df[(df["crop"] == crop) & (df["region"] == region)].copy()
    if sub.empty:
        return None, None
    sub["date"] = pd.to_datetime(sub["date"]).dt.normalize()
    # exact
    exact = sub[sub["date"].dt.date == target_date]
    if not exact.empty:
        row = exact.sort_values("date").iloc[-1]
        return float(row["price_pkr_per_40kg"]), target_date
    # nearest within 7 days
    target_ts = pd.Timestamp(target_date)
    sub = sub.assign(_diff=(sub["date"] - target_ts).abs())
    near = sub[sub["_diff"] <= pd.Timedelta(days=7)].sort_values("_diff")
    if near.empty:
        return None, None
    row = near.iloc[0]
    return float(row["price_pkr_per_40kg"]), row["date"].date()


def _price_range_stats(df, crop, region, start, end):
    """
    Stats over [start, end]. Returns dict or None if no rows.
    """
    import pandas as pd

    sub = df[(df["crop"] == crop) & (df["region"] == region)].copy()
    if sub.empty:
        return None
    sub["date"] = pd.to_datetime(sub["date"])
    sub = sub[
        (sub["date"].dt.date >= start) & (sub["date"].dt.date <= end)
    ].sort_values("date")
    if sub.empty:
        return None
    prices = sub["price_pkr_per_40kg"]
    return {
        "count": len(sub),
        "min": float(prices.min()),
        "max": float(prices.max()),
        "avg": float(prices.mean()),
        "first_date": sub["date"].iloc[0].date(),
        "last_date": sub["date"].iloc[-1].date(),
        "first_price": float(prices.iloc[0]),
        "last_price": float(prices.iloc[-1]),
    }


def answer_query(query_text, df, regions_to_check):
    """
    Main entry point. Takes the farmer's raw question and the dataset,
    returns a dict: {"answer": str, "matched_crop": str or None,
    "lang": "en"/"ur", "error": str or None}.

    Never raises — any failure path returns a dict with a clear "error"
    message instead, so the calling page can display something sensible
    rather than crashing.
    """
    lang = detect_language(query_text)

    # Step 1: get an English version of the query to match against crop names
    if lang == "ur":
        query_en = translate_text(query_text, "en")
        if query_en is None:
            # Gemini unavailable (no key / network issue) — fall back to the
            # local Roman Urdu synonym dictionary instead of giving up
            # entirely. This won't handle full sentences as well as real
            # translation, but it means "aloo price" still matches "Potato"
            # even with zero API dependency.
            query_en = expand_roman_urdu_crop_names(query_text)
    else:
        query_en = query_text

    # Step 2: match against known crops — using English names PLUS any
    # Urdu/Roman Urdu translations built by build_crop_translations.py
    known_crops = sorted(df["crop"].unique())
    translations = load_crop_translations()
    matched_crop, suggested_crop = match_crop(query_en, known_crops, translations)

    if not matched_crop and not suggested_crop:
        error_en = "Sorry, I couldn't identify which crop you're asking about. Try naming it more directly, e.g. 'apple price'."
        if lang == "ur":
            error_ur = translate_text(error_en, "ur")
            error_en = error_ur or error_en
        return {"answer": None, "matched_crop": None, "lang": lang, "error": error_en}

    if not matched_crop and suggested_crop:
        # Weak match only — ask "did you mean X?" instead of failing flat.
        # Show the suggestion in Urdu script too if we have a translation
        # for it, so the farmer recognizes the name even if their exact
        # wording didn't match.
        entry = translations.get(suggested_crop, {})
        crop_display = suggested_crop
        if entry.get("urdu"):
            crop_display = f"{suggested_crop} ({entry['urdu']})"

        error_en = f"I couldn't find an exact match. Did you mean **{crop_display}**? Try asking again using that name."
        if lang == "ur":
            error_ur = translate_text(error_en, "ur")
            error_en = error_ur or error_en
        return {"answer": None, "matched_crop": None, "lang": lang, "error": error_en}

    # Step 3: choose region — prefer a city mentioned in the question,
    # then fall back to Dashboard selection, then any region that has data.
    all_regions = sorted(df["region"].unique())
    region_from_query = match_region(query_text, all_regions)
    # Also try the English-translated query in case the original was Urdu
    if region_from_query is None and query_en != query_text:
        region_from_query = match_region(query_en, all_regions)

    if region_from_query:
        # Confirm this region actually has data for the matched crop
        region = find_valid_region(df, matched_crop, [region_from_query])
        if region is None:
            error_en = (
                f"I found '{matched_crop}' but there is no price data for it in "
                f"**{region_from_query}**. Try another city, or ask without naming a city."
            )
            if lang == "ur":
                error_ur = translate_text(error_en, "ur")
                error_en = error_ur or error_en
            return {"answer": None, "matched_crop": matched_crop, "lang": lang, "error": error_en}
    else:
        region = (
            find_valid_region(df, matched_crop, regions_to_check)
            or find_valid_region(df, matched_crop, all_regions)
        )

    if not region:
        error_en = f"I found the crop '{matched_crop}' but there's no price data available for it right now."
        if lang == "ur":
            error_ur = translate_text(error_en, "ur")
            error_en = error_ur or error_en
        return {"answer": None, "matched_crop": matched_crop, "lang": lang, "error": error_en}

    # Step 4: dates (optional) — single day or range; otherwise latest price
    date_mode, d1, d2 = parse_dates_from_query(query_text)
    if date_mode is None and query_en != query_text:
        date_mode, d1, d2 = parse_dates_from_query(query_en)

    if date_mode == "on":
        price, actual = _price_on_date(df, matched_crop, region, d1)
        if price is None:
            error_en = (
                f"No price data for **{matched_crop}** in **{region}** around "
                f"{d1.isoformat()}. Try another date or city."
            )
            if lang == "ur":
                error_ur = translate_text(error_en, "ur")
                error_en = error_ur or error_en
            return {"answer": None, "matched_crop": matched_crop, "lang": lang, "error": error_en}
        if actual == d1:
            answer_en = (
                f"On {d1.isoformat()}, the price of {matched_crop} in {region} "
                f"was PKR {price:,.0f} per 40kg."
            )
        else:
            answer_en = (
                f"No exact data for {d1.isoformat()}. Nearest available: "
                f"{actual.isoformat()} — {matched_crop} in {region} was "
                f"PKR {price:,.0f} per 40kg."
            )

    elif date_mode == "range":
        stats_r = _price_range_stats(df, matched_crop, region, d1, d2)
        if stats_r is None:
            error_en = (
                f"No price data for **{matched_crop}** in **{region}** between "
                f"{d1.isoformat()} and {d2.isoformat()}."
            )
            if lang == "ur":
                error_ur = translate_text(error_en, "ur")
                error_en = error_ur or error_en
            return {"answer": None, "matched_crop": matched_crop, "lang": lang, "error": error_en}
        change = stats_r["last_price"] - stats_r["first_price"]
        change_pct = (change / stats_r["first_price"] * 100) if stats_r["first_price"] else 0
        answer_en = (
            f"From {d1.isoformat()} to {d2.isoformat()}, {matched_crop} in {region}: "
            f"average PKR {stats_r['avg']:,.0f}, min PKR {stats_r['min']:,.0f}, "
            f"max PKR {stats_r['max']:,.0f} per 40kg "
            f"({stats_r['count']} day(s) of data). "
            f"Start PKR {stats_r['first_price']:,.0f} → end PKR {stats_r['last_price']:,.0f} "
            f"({change_pct:+.1f}%)."
        )

    else:
        # Default: latest price + trend + advisory (original behaviour)
        stats = get_crop_stats(df, matched_crop, region)
        if stats is None:
            error_en = f"I found '{matched_crop}' in {region}, but could not compute price stats."
            return {"answer": None, "matched_crop": matched_crop, "lang": lang, "error": error_en}

        forecast = get_forecast(stats["hist"])
        advice, _ = rule_based_advice(stats["chg_7d"], stats["recent_slope"])

        chg_7d_text = f"{stats['chg_7d']:+.1f}%" if stats["chg_7d"] is not None else "not enough recent data to calculate"
        forecast_text = ""
        if forecast is not None:
            trend_word = "rising" if forecast["slope"] > 0 else "falling" if forecast["slope"] < 0 else "stable"
            forecast_text = f" The short-term forecast suggests prices are {trend_word}."

        answer_en = (
            f"The current price of {matched_crop} in {region} is PKR {stats['latest_price']:,.0f} per 40kg. "
            f"Over the last 7 days, the price has changed by {chg_7d_text}.{forecast_text} "
            f"Advisory: {advice}"
        )

    # Step 5: translate the answer back to Urdu if that's what was asked
    answer = answer_en
    if lang == "ur":
        answer_ur = translate_text(answer_en, "ur")
        answer = answer_ur or answer_en  # fall back to English if translation fails, rather than showing nothing

    return {"answer": answer, "matched_crop": matched_crop, "lang": lang, "error": None}
