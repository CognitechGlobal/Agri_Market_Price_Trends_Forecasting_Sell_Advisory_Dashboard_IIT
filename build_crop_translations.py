"""
build_crop_translations.py
---------------------------
One-time (re-run when your crop list changes) script: reads every unique
crop name from your combined dataset, asks Gemini for the Urdu script name
and a common Roman Urdu spelling for each, and saves the result to
crop_translations.json.

WHY A SEPARATE BUILD STEP, NOT DONE LIVE IN THE APP?
Translating ~50-80 crop names via Gemini takes real time and API calls.
Doing it once and caching to a file means:
  - the live app loads instantly (no translation happening during a
    farmer's actual question)
  - it doesn't burn API quota re-translating the same names over and over
  - you can review/correct the file by hand if a translation looks off,
    before your app ever uses it

Run with:  python build_crop_translations.py
Needs GEMINI_API_KEY set (same as your other AI features) — set it with
`setx GEMINI_API_KEY "your-key"` locally, same as before.

Re-run this whenever you add more crops (e.g. after combining more of your
53 source files) — it's safe to re-run; it only re-translates crops that
aren't already in the output file, so it won't waste API calls redoing
crops you already have.
"""

import json
import os
import time
import pandas as pd
from ai_advisory import call_gemini_raw

INPUT_CSV = "real_mandi_prices.csv"
OUTPUT_FILE = "crop_translations.json"


def build_translation_prompt(crop_name):
    return f"""Give the Urdu script name and common Roman Urdu (Urdu written in English letters) spellings for this crop/food item, as commonly used in everyday Pakistani market speech.

Crop: {crop_name}

Respond in EXACTLY this format, nothing else, no explanation:
URDU: <urdu script name>
ROMAN: <comma-separated list of 2-3 common alternate Roman Urdu spellings, lowercase>

Example for "Apple": 
URDU: سیب
ROMAN: seb, saib, sayb

If the crop name includes a variety in parentheses (e.g. "Apple (Golden)"), translate the base crop name naturally, and if there's a common Urdu term for that specific variety include it — otherwise just give the base crop's translation.
"""


def parse_response(text):
    urdu, roman_variants = None, []
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("URDU:"):
            urdu = line.split(":", 1)[1].strip()
        elif line.upper().startswith("ROMAN:"):
            raw = line.split(":", 1)[1].strip().lower()
            roman_variants = [v.strip() for v in raw.split(",") if v.strip()]
    return urdu, roman_variants


def main():
    df = pd.read_csv(INPUT_CSV)
    crops = sorted(df["Crop"].dropna().unique())
    print(f"Found {len(crops)} unique crops in {INPUT_CSV}.")

    # Load existing translations so re-running doesn't waste API calls
    # re-translating crops you already have.
    existing = {}
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
        print(f"Loaded {len(existing)} existing translations — will skip those.")

    to_translate = [c for c in crops if c not in existing]
    print(f"{len(to_translate)} crop(s) need translating.\n")

    if not to_translate:
        print("Nothing new to translate. Done.")
        return

    translations = dict(existing)
    failed = []

    for i, crop in enumerate(to_translate, 1):
        print(f"[{i}/{len(to_translate)}] Translating: {crop}")
        response = call_gemini_raw(build_translation_prompt(crop))
        if response is None:
            print(f"  ⚠️ Failed — check GEMINI_API_KEY is set correctly.")
            failed.append(crop)
            continue
        urdu, roman_variants = parse_response(response)
        if not urdu or not roman_variants:
            print(f"  ⚠️ Unexpected response format: {response!r}")
            failed.append(crop)
            continue
        translations[crop] = {"urdu": urdu, "roman_urdu": roman_variants}
        print(f"  -> Urdu: {urdu}  |  Roman variants: {', '.join(roman_variants)}")
        time.sleep(1)  # be gentle with rate limits — no need to rush a one-time script

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(translations, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved {len(translations)} total translations to {OUTPUT_FILE}")
    if failed:
        print(f"⚠️ {len(failed)} crop(s) failed to translate: {failed}")
        print("   Re-run this script again to retry just those (already-translated ones are skipped).")


if __name__ == "__main__":
    main()
