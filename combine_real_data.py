"""
combine_real_data.py
---------------------
Combines all per-crop mandi price CSV files (City, Date, Crop, Price columns)
into a single master file: real_mandi_prices.csv

WHAT THIS DOES, STEP BY STEP:
1. Finds every .csv file in the given folder
2. Checks each file has the expected columns (City, Date, Crop, Price) —
   flags anything that doesn't match instead of silently breaking
3. Stacks them all into one big table
4. Cleans it up: proper date format, drops rows with missing/zero prices,
   removes exact duplicate rows
5. Saves the result + prints a summary so you can sanity-check it

Run with:  python combine_real_data.py
By default it looks for CSVs in the same folder as this script. If your 53
files are in a different folder, change DATA_FOLDER below.
"""

import pandas as pd
import glob
import os

DATA_FOLDER = "./data"
OUTPUT_FILE = "real_mandi_prices.csv"
EXPECTED_COLUMNS = {"City", "Date", "Crop", "Price"}

# ---------------------------------------------------------------------------
# 1. FIND ALL CSV FILES
# ---------------------------------------------------------------------------
csv_files = glob.glob(os.path.join(DATA_FOLDER, "*.csv"))
# don't accidentally re-combine our own output if you run this twice
csv_files = [f for f in csv_files if os.path.basename(f) != OUTPUT_FILE]

print(f"Found {len(csv_files)} CSV files.")
if len(csv_files) == 0:
    raise SystemExit("No CSV files found — check DATA_FOLDER points to the right place.")

# ---------------------------------------------------------------------------
# 2. LOAD EACH FILE, VALIDATE COLUMNS, COLLECT INTO A LIST
# ---------------------------------------------------------------------------
frames = []
bad_files = []

for f in csv_files:
    try:
        df = pd.read_csv(f)
    except Exception as e:
        bad_files.append((f, f"couldn't read file: {e}"))
        continue

    cols = set(df.columns.str.strip())
    if cols != EXPECTED_COLUMNS:
        bad_files.append((f, f"unexpected columns: {list(df.columns)}"))
        continue

    frames.append(df)

if bad_files:
    print(f"\n⚠️  {len(bad_files)} file(s) had problems and were SKIPPED:")
    for f, reason in bad_files:
        print(f"   - {os.path.basename(f)}: {reason}")
    print("   Fix these separately if you need that data — the rest will still combine fine.\n")

print(f"Successfully loaded {len(frames)} of {len(csv_files)} files.")

# ---------------------------------------------------------------------------
# 3. COMBINE INTO ONE TABLE
# ---------------------------------------------------------------------------
combined = pd.concat(frames, ignore_index=True)
print(f"Combined shape before cleaning: {combined.shape[0]} rows")

# ---------------------------------------------------------------------------
# 4. CLEAN UP
# ---------------------------------------------------------------------------
# Standardize column names (in case of stray whitespace)
combined.columns = [c.strip() for c in combined.columns]

# Parse dates properly; anything that fails to parse becomes NaT (Not a Time)
combined["Date"] = pd.to_datetime(combined["Date"], errors="coerce")

# Drop rows with missing City/Crop/Date/Price, or price <= 0 (bad data entries)
before = len(combined)
combined = combined.dropna(subset=["City", "Date", "Crop", "Price"])
combined = combined[combined["Price"] > 0]
after_missing_drop = len(combined)

# Remove exact duplicate rows (same city, date, crop, price repeated)
combined = combined.drop_duplicates()
after_dedup = len(combined)

print(f"Dropped {before - after_missing_drop} rows with missing/invalid data")
print(f"Dropped {after_missing_drop - after_dedup} exact duplicate rows")
print(f"Final combined shape: {combined.shape[0]} rows")

# ---------------------------------------------------------------------------
# 5. SAVE + SUMMARY
# ---------------------------------------------------------------------------
combined = combined.sort_values(["Crop", "City", "Date"]).reset_index(drop=True)
combined.to_csv(OUTPUT_FILE, index=False)

print(f"\n✅ Saved combined dataset -> {OUTPUT_FILE}")
print(f"\nSummary:")
print(f"  Unique crops:  {combined['Crop'].nunique()}")
print(f"  Unique cities: {combined['City'].nunique()}")
print(f"  Date range:    {combined['Date'].min().date()} to {combined['Date'].max().date()}")
print(f"\nSample crops: {sorted(combined['Crop'].unique())[:10]}")
print(f"Sample cities: {sorted(combined['City'].unique())[:10]}")
