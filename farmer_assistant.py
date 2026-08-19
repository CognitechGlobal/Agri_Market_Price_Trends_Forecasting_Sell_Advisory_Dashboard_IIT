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
4. Pull the actual stats for that crop using price_utils (the SAME
   calculation logic the dashboard charts use).
5. Build a plain-English answer sentence from those stats.
6. If the original question was in Urdu, translate the answer back to Urdu
   using Gemini before returning it.

WHY GEMINI FOR TRANSLATION INSTEAD OF A TRANSLATION LIBRARY?
Keeps the dependency list small (already using Gemini for AI insights) and
Gemini handles agricultural terms in Urdu reasonably well. The tradeoff:
translation requires an API key and a network call, so this feature quietly
degrades to "crop not understood" if no key is configured — it does not
crash the app.
"""

import re
import difflib
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


def match_crop(query_en, known_crops):
    """
    Fuzzy-matches a free-text query against the list of known crop names.

    Rather than stopping at the FIRST substring match (which incorrectly
    matched "apple golden" to "Apple (Ammre)" just because both start with
    "apple"), this scores every crop by how many of its words appear in the
    query, and returns the crop with the strongest overall match. Typos are
    handled by fuzzy-matching individual words (via difflib) rather than
    comparing whole crop names, since "aple" vs "apple (ammre)" scores very
    differently than "aple" vs "apple".
    """
    query_words = re.findall(r"\w+", query_en.lower())
    if not query_words:
        return None

    best_crop, best_score = None, 0

    for crop in known_crops:
        # Break "Apple (Golden)" into ["apple", "golden"] — punctuation stripped
        crop_words = re.findall(r"\w+", crop.lower())
        score = 0
        for cw in crop_words:
            if cw in query_words:
                score += 2  # exact word match — strong signal
            else:
                # fuzzy match against each query word for typo tolerance
                close = difflib.get_close_matches(cw, query_words, n=1, cutoff=0.75)
                if close:
                    score += 1  # fuzzy match — weaker signal than exact

        if score > best_score:
            best_score = score
            best_crop = crop

    return best_crop if best_score > 0 else None


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

    # Step 2: match against known crops
    known_crops = sorted(df["crop"].unique())
    matched_crop = match_crop(query_en, known_crops)
    if not matched_crop:
        error_en = "Sorry, I couldn't identify which crop you're asking about. Try naming it more directly, e.g. 'wheat price'."
        if lang == "ur":
            error_ur = translate_text(error_en, "ur")
            error_en = error_ur or error_en
        return {"answer": None, "matched_crop": None, "lang": lang, "error": error_en}

    # Step 3: get real stats for that crop (same logic as the dashboard)
    region = find_valid_region(df, matched_crop, regions_to_check) or find_valid_region(df, matched_crop, sorted(df["region"].unique()))
    if not region:
        error_en = f"I found the crop '{matched_crop}' but there's no price data available for it right now."
        if lang == "ur":
            error_ur = translate_text(error_en, "ur")
            error_en = error_ur or error_en
        return {"answer": None, "matched_crop": matched_crop, "lang": lang, "error": error_en}

    stats = get_crop_stats(df, matched_crop, region)
    forecast = get_forecast(stats["hist"])
    advice, _ = rule_based_advice(stats["chg_7d"], stats["recent_slope"])

    # Step 4: build a plain English answer
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
