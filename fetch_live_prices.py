"""
fetch_live_prices.py
---------------------
Fetches today's live mandi rates from kissancares.com/mandi-rates and
converts them into the same format as your historical dataset, so they can
be merged in or viewed separately.

⚠️ IMPORTANT — READ BEFORE USING:
1. This scrapes a public webpage, not an official API (no free official
   Pakistan mandi price API currently exists). Check
   https://kissancares.com/robots.txt and their Terms & Conditions
   yourself before relying on this for anything beyond a student project —
   scraping policies vary and I can't verify this site's specific terms.
2. This only covers 5 crops: Wheat, Rice, Maize, Cotton, Sugarcane. Your
   other 53 crops (apples, apricots, etc.) have NO live source available —
   this supplements your historical data for these 5 crops only, it
   doesn't replace your full dataset.
3. This scrapes the page's HTML structure as it exists today. If the site
   redesigns their page, this script will likely break and need updating —
   that's the nature of scraping (vs. a stable API), not a bug to "fix"
   once and never think about again.
4. I could not test this against the live site myself (sandboxed
   environment can't reach external websites) — built from a real page
   fetch, but YOU need to be the one to confirm it actually works.

Run with:  python fetch_live_prices.py
Saves result to: live_mandi_prices.csv
"""

import re
import sys
import pandas as pd
import requests
from io import StringIO

SOURCE_URL = "https://kissancares.com/mandi-rates"
OUTPUT_FILE = "live_mandi_prices.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AgriDashboardStudentProject/1.0; +educational use)"
}


def clean_crop_name(raw_crop):
    """Table shows crops like 'Sugarcane (گنا)' — strip the Urdu parenthetical."""
    return re.sub(r"\s*\([^)]*\)\s*", "", raw_crop).strip()


def clean_price(raw_price):
    r"""
    Converts 'Rs. 3,220' -> 3220.0. Returns None if it can't parse.

    BUG THIS FIXES: naively stripping everything except digits and dots
    (re.sub(r"[^\d.]", "", ...)) keeps the period in "Rs." itself, turning
    "Rs. 3,220" into ".3220" -> 0.322 instead of 3220 — silently wrong by a
    factor of ~10,000, not an error that would be obvious at a glance.
    Extracting the actual number pattern after "Rs." avoids this.
    """
    if pd.isna(raw_price):
        return None
    match = re.search(r"[\d,]+(?:\.\d+)?", str(raw_price).replace("Rs.", "").replace("Rs", ""))
    if not match:
        return None
    digits = match.group(0).replace(",", "")
    return float(digits) if digits else None


def fetch_live_mandi_table():
    """Fetches the page and returns the raw price table as a DataFrame."""
    response = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    # StringIO wrapper: some pandas versions try to interpret a raw string
    # as a file path/URL instead of literal HTML content, causing a
    # confusing "No such file or directory" error even though the HTML is
    # perfectly valid. Wrapping in StringIO forces it to be treated as
    # literal content regardless of pandas version.
    tables = pd.read_html(StringIO(response.text))

    for table in tables:
        cols = [str(c).lower() for c in table.columns]
        if any("mandi rate" in c for c in cols) and any("crop" in c or "commodity" in c for c in cols):
            return table

    raise ValueError(
        "Couldn't find the price table on the page. The site may have changed "
        "its layout — this script needs updating if so."
    )


def transform_to_app_schema(raw_table):
    """Converts the scraped table's columns into City, Date, Crop, Price."""
    df = raw_table.copy()

    col_map = {}
    for col in df.columns:
        col_lower = str(col).lower()
        if "crop" in col_lower or "commodity" in col_lower:
            col_map[col] = "Crop"
        elif "mandi" in col_lower and "city" in col_lower:
            col_map[col] = "City"
        elif "mandi rate" in col_lower:
            col_map[col] = "Price"
        elif "recording date" in col_lower or "date" in col_lower:
            col_map[col] = "Date"

    df = df.rename(columns=col_map)
    required = {"Crop", "City", "Price", "Date"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Expected columns not found after mapping: {missing}. Found columns: {list(raw_table.columns)}")

    df = df[["City", "Date", "Crop", "Price"]].copy()
    df["Crop"] = df["Crop"].apply(clean_crop_name)
    df["Price"] = df["Price"].apply(clean_price)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["City"] = df["City"].astype(str).str.strip()

    df = df.dropna(subset=["City", "Date", "Crop", "Price"])
    df = df[df["Price"] > 0]

    return df


def main():
    print(f"Fetching live mandi rates from {SOURCE_URL} ...")
    try:
        raw_table = fetch_live_mandi_table()
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error fetching the page: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    print(f"Found raw table with {len(raw_table)} rows. Transforming...")
    try:
        clean_df = transform_to_app_schema(raw_table)
    except ValueError as e:
        print(f"❌ {e}")
        print("Raw columns found:", list(raw_table.columns))
        sys.exit(1)

    clean_df.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✅ Saved {len(clean_df)} live price rows to {OUTPUT_FILE}")
    print(f"Crops covered: {sorted(clean_df['Crop'].unique())}")
    print(f"Cities covered: {clean_df['City'].nunique()}")
    print(f"Date range: {clean_df['Date'].min().date()} to {clean_df['Date'].max().date()}")


if __name__ == "__main__":
    main()
