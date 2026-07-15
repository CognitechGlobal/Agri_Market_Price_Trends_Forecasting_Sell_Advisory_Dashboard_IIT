"""
generate_mock_data.py
----------------------
Generates a realistic mock dataset of daily mandi (wholesale market) prices
for key crops across major Pakistani regions.

WHY MOCK DATA FIRST?
The project brief flags "data freshness/accuracy" as a real risk. Real mandi
price scraping (pakissan.com, PBS reports, govt portals) is inconsistent in
format and availability. For an MVP, the standard move is: build on realistic
mock/synthetic data now so the *dashboard, charts, and advisory logic* can be
built and tested immediately -> swap in real scraped/uploaded data later
without changing any downstream code. This is exactly what your brief's
"Potential Challenges & Mitigations" section recommends.

Run this once to create mandi_prices.csv, which app.py reads.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ---- 1. Define scope: 8 crops x 6 regions (fits the "6-8 crops, 4-6 mandis" ask) ----
CROPS = {
    # crop: (base_price_pkr_per_40kg, volatility, seasonal_amplitude)
    "Wheat":     (2800, 0.01, 0.05),
    "Rice":      (4200, 0.015, 0.06),
    "Potato":    (1800, 0.04, 0.20),   # potato is famously volatile (blight, storage issues)
    "Tomato":    (2200, 0.06, 0.35),   # tomato swings hardest, good for demo drama
    "Onion":     (2500, 0.05, 0.25),
    "Sugarcane": (400,  0.01, 0.04),
    "Maize":     (2100, 0.015, 0.08),
    "Chili":     (12000, 0.03, 0.15),
}

REGIONS = ["Lahore", "Faisalabad", "Rawalpindi/Islamabad", "Multan", "Gujranwala", "Karachi"]

# Each region has a small structural price offset (transport cost, local demand)
REGION_OFFSET = {
    "Lahore": 0.00,
    "Faisalabad": -0.03,
    "Rawalpindi/Islamabad": 0.05,   # slightly pricier, closer to consumption hub
    "Multan": -0.05,                # closer to production zones, cheaper
    "Gujranwala": -0.02,
    "Karachi": 0.08,                # furthest from Punjab production belt
}

DAYS = 120  # ~4 months of daily history, enough for 7/30-day trend views
START_DATE = datetime.today() - timedelta(days=DAYS)

rng = np.random.default_rng(seed=42)  # fixed seed = reproducible demo data

rows = []
for crop, (base, vol, seasonal_amp) in CROPS.items():
    for region in REGIONS:
        offset = REGION_OFFSET[region]
        # Give potato a scripted "blight event" mid-way through, so the
        # AI advisory / news-feed features have something meaningful to react to.
        blight_day = DAYS // 2 if crop == "Potato" else None

        price = base * (1 + offset)
        for day in range(DAYS):
            date = START_DATE + timedelta(days=day)

            # Seasonal wave (e.g. harvest season lowers price, off-season raises it)
            seasonal = seasonal_amp * np.sin(2 * np.pi * day / 60)

            # Day-to-day random walk (volatility)
            shock = rng.normal(0, vol)

            # Scripted supply-shock event for Potato (simulates the brief's
            # example: "possible early blight supply drop")
            event_bump = 0
            if blight_day is not None and blight_day <= day <= blight_day + 15:
                event_bump = 0.25 * (1 - abs(day - (blight_day + 7)) / 8)  # spike then settle

            daily_change = seasonal / 60 + shock + event_bump / 15
            price = max(price * (1 + daily_change), base * 0.4)  # floor so prices don't go absurd

            rows.append({
                "date": date.strftime("%Y-%m-%d"),
                "crop": crop,
                "region": region,
                "price_pkr_per_40kg": round(price, 1),
            })

df = pd.DataFrame(rows)
df.to_csv("mandi_prices.csv", index=False)
print(f"Generated {len(df)} rows -> mandi_prices.csv")
print(df.head())
