"""
price_utils.py
--------------
Core price calculation logic, shared between the main Dashboard page and the
new "Ask About a Crop" Q&A page. Extracted from app.py so both pages compute
stats the SAME way — a farmer asking "what's the potato forecast" should get
an answer that matches what the dashboard chart shows, not a second,
slightly-different calculation living in a separate file.
"""

import numpy as np
from datetime import timedelta


def find_valid_region(df, crop, regions):
    """Returns the first region (from the given list) that actually has data
    for this crop, or None if none of them do. Real data has gaps — not every
    crop is reported in every city — so we can't just blindly use regions[0]."""
    for r in regions:
        if ((df["crop"] == crop) & (df["region"] == r)).any():
            return r
    return None


def get_crop_stats(df, crop, region):
    """
    Computes the core stats for one crop/region: latest price, 7-day and
    30-day % change, and the recent trend slope (used by forecasting and
    advisory). Returns a dict, or None if there's no data at all for this
    combo (caller should handle that case with a clear message).
    """
    region_df = df[(df["crop"] == crop) & (df["region"] == region)].sort_values("date")
    if region_df.empty:
        return None

    latest_price = region_df["price_pkr_per_40kg"].iloc[-1]
    latest_date = region_df["date"].iloc[-1]

    def price_n_days_before(n_days):
        subset = region_df[region_df["date"] <= latest_date - timedelta(days=n_days)]
        if subset.empty:
            return None
        return subset["price_pkr_per_40kg"].iloc[-1]

    price_7d_ago = price_n_days_before(7)
    price_30d_ago = price_n_days_before(30)

    chg_7d = (latest_price - price_7d_ago) / price_7d_ago * 100 if price_7d_ago else None
    chg_30d = (latest_price - price_30d_ago) / price_30d_ago * 100 if price_30d_ago else None

    # Recent slope of the 7-day moving average — used by both the forecast
    # chart and the rule-based advisory below.
    hist = region_df.tail(30).copy()
    hist["ma7"] = hist["price_pkr_per_40kg"].rolling(7).mean()
    recent_slope = (hist["ma7"].iloc[-1] - hist["ma7"].iloc[-8]) / 7 if len(hist) >= 8 else 0

    return {
        "region_df": region_df,
        "hist": hist,
        "latest_price": latest_price,
        "latest_date": latest_date,
        "chg_7d": chg_7d,
        "chg_30d": chg_30d,
        "recent_slope": recent_slope,
    }


def get_forecast(hist):
    """
    Builds a simple 7-day-ahead forecast using linear regression on the last
    14 days. Returns None if there's not enough data (fewer than 2 points).
    Returns a dict with future dates/prices, plus resid_std (how much the
    regression line missed real points by) for building a confidence band.
    """
    lr_window = hist.tail(14).dropna(subset=["price_pkr_per_40kg"]).reset_index(drop=True)
    if len(lr_window) < 2:
        return None

    x = np.arange(len(lr_window))
    y = lr_window["price_pkr_per_40kg"].values
    slope, intercept = np.polyfit(x, y, 1)
    residuals = y - (slope * x + intercept)
    resid_std = residuals.std()

    future_x = np.arange(len(lr_window), len(lr_window) + 7)
    future_prices = slope * future_x + intercept
    future_dates = [lr_window["date"].iloc[-1] + timedelta(days=i) for i in range(1, 8)]

    return {"dates": future_dates, "prices": future_prices, "slope": slope, "resid_std": resid_std}


def rule_based_advice(chg_7d, recent_slope):
    """Returns (advice_text, color) — the same logic used on the dashboard,
    now reusable so the Q&A page gives a consistent answer."""
    if chg_7d is None:
        return "NOT ENOUGH DATA — need at least 7 days of price history for this crop/region to give advisory.", "gray"
    elif chg_7d > 5 and recent_slope > 0:
        return "HOLD — price is rising, consider waiting a few more days.", "green"
    elif chg_7d < -5:
        return "SELL SOON — price has been falling; further drops possible.", "red"
    else:
        return "MONITOR — price is relatively stable right now.", "orange"
