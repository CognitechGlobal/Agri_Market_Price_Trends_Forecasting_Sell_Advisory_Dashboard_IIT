"""
app.py
------
Agri Market Price Trends, Forecasting & Sell Advisory Dashboard (MVP - Week 1)

This is a Week 1 skeleton: it covers the MVP must-haves that don't yet need
the AI/Gemini layer (that's Week 3 per your brief). What's here:
  1. Filters: crop, region/mandi, date range
  2. Current price + 7/30-day trend charts (interactive, Plotly)
  3. Simple forecasting: moving-average projection
  4. Rule-based sell advisory (placeholder for the Gemini layer later)
  5. Cross-mandi comparison
  6. Mock news/alerts feed
  7. CSV export

Run with:  streamlit run app.py
(Make sure you've run generate_mock_data.py first to create mandi_prices.csv)
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import timedelta

st.set_page_config(page_title="Agri Price Advisory", layout="wide", page_icon="🌾")

# ---------------------------------------------------------------------------
# 1. LOAD DATA
# ---------------------------------------------------------------------------
@st.cache_data
def load_data():
    # Using the real combined dataset (from combine_real_data.py) instead of
    # the mock data now. The real file uses different column names
    # (City, Date, Crop, Price) — rename them here so nothing else in the
    # app below needs to change.
    df = pd.read_csv("real_mandi_prices.csv", parse_dates=["Date"])
    df = df.rename(columns={
        "City": "region",
        "Date": "date",
        "Crop": "crop",
        "Price": "price_pkr_per_40kg",
    })
    return df

df = load_data()

# ---------------------------------------------------------------------------
# 2. SIDEBAR FILTERS
# ---------------------------------------------------------------------------
st.sidebar.title("🌾 Filters")

crop = st.sidebar.selectbox("Crop", sorted(df["crop"].unique()))

all_regions = sorted(df["region"].unique())
regions = st.sidebar.multiselect("Region(s) / Mandi", all_regions, default=all_regions[:3])

min_date, max_date = df["date"].min(), df["date"].max()

# UPGRADE: swapped the single slider for two separate date pickers.
# With 15 years of real data, a single slider's drag handles become
# extremely sensitive (a tiny mouse movement = months of date change),
# making the "start" handle feel stuck. Two date_input boxes let you type
# or pick an exact date instead, which is far more reliable.
col_start, col_end = st.sidebar.columns(2)
start_date = col_start.date_input(
    "From", value=(max_date - timedelta(days=30)).date(),
    min_value=min_date.date(), max_value=max_date.date(),
)
end_date = col_end.date_input(
    "To", value=max_date.date(),
    min_value=min_date.date(), max_value=max_date.date(),
)

if start_date > end_date:
    st.sidebar.error("'From' date must be before 'To' date.")
    st.stop()

date_range = (pd.Timestamp(start_date), pd.Timestamp(end_date))

if not regions:
    st.warning("Select at least one region from the sidebar.")
    st.stop()

filtered = df[
    (df["crop"] == crop)
    & (df["region"].isin(regions))
    & (df["date"] >= date_range[0])
    & (df["date"] <= date_range[1])
].copy()

st.title("Agri Market Price Trends & Sell Advisory")
st.caption("MVP dashboard — now running on real combined mandi price data.")

# ---------------------------------------------------------------------------
# 3. KPI CARDS (current price + 7/30-day change)
# ---------------------------------------------------------------------------
# Real data has gaps: not every crop was reported in every region on every
# date. So instead of blindly using the first selected region, we pick the
# first one that actually HAS data for this crop — and warn instead of
# crashing if none of the selected regions have any data at all.
valid_regions = [r for r in regions if ((df["crop"] == crop) & (df["region"] == r)).any()]

if not valid_regions:
    st.warning(
        f"No price data found for **{crop}** in any of the selected regions. "
        "Try picking a different region or crop from the sidebar."
    )
    st.stop()

primary_region = valid_regions[0]
region_df = df[(df["crop"] == crop) & (df["region"] == primary_region)].sort_values("date")

latest_price = region_df["price_pkr_per_40kg"].iloc[-1]
latest_date = region_df["date"].iloc[-1]  # use THIS region/crop's own latest date,
                                            # not the global max_date, since real data
                                            # doesn't all end on the same day

def price_n_days_before(n_days):
    """Returns the most recent price at or before (latest_date - n_days),
    or None if there's no data that far back — avoids IndexError crashes
    on short/gappy histories."""
    subset = region_df[region_df["date"] <= latest_date - timedelta(days=n_days)]
    if subset.empty:
        return None
    return subset["price_pkr_per_40kg"].iloc[-1]

price_7d_ago = price_n_days_before(7)
price_30d_ago = price_n_days_before(30)

chg_7d = (latest_price - price_7d_ago) / price_7d_ago * 100 if price_7d_ago else None
chg_30d = (latest_price - price_30d_ago) / price_30d_ago * 100 if price_30d_ago else None

col1, col2, col3 = st.columns(3)
col1.metric(f"Current price ({primary_region})", f"PKR {latest_price:,.0f}/40kg")
col2.metric("7-day change", f"{chg_7d:+.1f}%" if chg_7d is not None else "N/A (not enough history)")
col3.metric("30-day change", f"{chg_30d:+.1f}%" if chg_30d is not None else "N/A (not enough history)")

# ---------------------------------------------------------------------------
# 4. TREND CHART (line, multi-region, colored green/red by direction)
# ---------------------------------------------------------------------------
st.subheader(f"{crop} price trend")

# UPGRADE: color each region's line green if price rose over the visible
# window, red if it fell. This gives an instant "who's up, who's down" read
# without having to trace each line back to its starting point.
fig = go.Figure()
for r in regions:
    r_df = filtered[filtered["region"] == r].sort_values("date")
    if len(r_df) < 2:
        line_color = "gray"
    else:
        rose = r_df["price_pkr_per_40kg"].iloc[-1] >= r_df["price_pkr_per_40kg"].iloc[0]
        line_color = "#2ecc71" if rose else "#e74c3c"  # green / red
    fig.add_trace(go.Scatter(
        x=r_df["date"], y=r_df["price_pkr_per_40kg"],
        mode="lines", name=r, line=dict(color=line_color, width=2.5),
    ))
fig.update_layout(
    yaxis_title="PKR per 40kg", xaxis_title="Date",
    hovermode="x unified", height=420,
)
st.plotly_chart(fig, use_container_width=True)
st.caption("🟢 Green = price rose over the selected date range · 🔴 Red = price fell")

# ---------------------------------------------------------------------------
# 5. MANDI COMPARISON (bar chart, current prices across all regions)
# ---------------------------------------------------------------------------
st.subheader(f"Current {crop} price by mandi")
latest_by_region = (
    df[df["crop"] == crop]
    .sort_values("date")
    .groupby("region")
    .tail(1)
    .sort_values("price_pkr_per_40kg")
)
fig2 = go.Figure(go.Bar(x=latest_by_region["region"], y=latest_by_region["price_pkr_per_40kg"]))
fig2.update_layout(yaxis_title="PKR per 40kg", height=350)
st.plotly_chart(fig2, use_container_width=True)

# ---------------------------------------------------------------------------
# 6. SIMPLE FORECAST: 7-day moving average projected forward
# ---------------------------------------------------------------------------
st.subheader("Simple forecast (7-day moving average)")

hist = region_df.tail(30).copy()
hist["ma7"] = hist["price_pkr_per_40kg"].rolling(7).mean()

# naive projection: extend the most recent MA slope forward 7 days
recent_slope = (hist["ma7"].iloc[-1] - hist["ma7"].iloc[-8]) / 7 if len(hist) >= 8 else 0
future_dates = [hist["date"].iloc[-1] + timedelta(days=i) for i in range(1, 8)]
future_prices = [hist["ma7"].iloc[-1] + recent_slope * i for i in range(1, 8)]

# UPGRADE: a second forecasting method — simple linear regression on the
# last 14 days — plotted alongside the moving-average projection. Having two
# methods agree (or disagree) is itself useful signal, and it looks more
# rigorous than a single naive line.
lr_window = hist.tail(14).dropna(subset=["price_pkr_per_40kg"]).reset_index(drop=True)

if len(lr_window) < 2:
    st.info(f"Not enough price history for {crop} in {primary_region} to build a forecast yet (need at least 2 data points).")
else:
    x = np.arange(len(lr_window))
    y = lr_window["price_pkr_per_40kg"].values
    slope, intercept = np.polyfit(x, y, 1)  # simple least-squares line: y = slope*x + intercept

    # residual std dev -> rough confidence band width (not a rigorous CI, just a
    # visual signal that this is a forecast, not a guarantee)
    residuals = y - (slope * x + intercept)
    resid_std = residuals.std()

    future_x = np.arange(len(lr_window), len(lr_window) + 7)
    lr_future_prices = slope * future_x + intercept
    lr_future_dates = [lr_window["date"].iloc[-1] + timedelta(days=i) for i in range(1, 8)]

    # confidence band widens the further out the forecast goes, since we're
    # less sure about day 7 than day 1
    band_width = resid_std * (1 + 0.15 * np.arange(1, 8))
    lr_upper = lr_future_prices + band_width
    lr_lower = lr_future_prices - band_width

    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(x=hist["date"], y=hist["price_pkr_per_40kg"], name="Actual price", mode="lines"))
    fig3.add_trace(go.Scatter(x=hist["date"], y=hist["ma7"], name="7-day MA", mode="lines", line=dict(dash="dot")))
    fig3.add_trace(go.Scatter(x=future_dates, y=future_prices, name="Forecast (moving avg)", mode="lines", line=dict(dash="dash", color="orange")))
    fig3.add_trace(go.Scatter(x=lr_future_dates, y=lr_future_prices, name="Forecast (linear regression)", mode="lines", line=dict(dash="dash", color="purple")))

    # confidence band: draw upper then lower with fill="tonexty" to shade between them
    fig3.add_trace(go.Scatter(x=lr_future_dates, y=lr_upper, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig3.add_trace(go.Scatter(
        x=lr_future_dates, y=lr_lower, mode="lines", line=dict(width=0),
        fill="tonexty", fillcolor="rgba(128,0,128,0.15)", name="Confidence band", hoverinfo="skip",
    ))

    fig3.update_layout(yaxis_title="PKR per 40kg", height=400)
    st.plotly_chart(fig3, use_container_width=True)
    st.caption("Two forecasting methods shown for comparison. The shaded band is a rough confidence range (not a statistical guarantee) — wider further out, since near-term forecasts are more reliable than longer-term ones.")

# ---------------------------------------------------------------------------
# 7. RULE-BASED SELL ADVISORY (placeholder for Week 3 Gemini upgrade)
# ---------------------------------------------------------------------------
st.subheader("Sell advisory")

if chg_7d is None:
    advice, color = "NOT ENOUGH DATA — need at least 7 days of price history for this crop/region to give advisory.", "gray"
elif chg_7d > 5 and recent_slope > 0:
    advice, color = "HOLD — price is rising, consider waiting a few more days.", "green"
elif chg_7d < -5:
    advice, color = "SELL SOON — price has been falling; further drops possible.", "red"
else:
    advice, color = "MONITOR — price is relatively stable right now.", "orange"

st.markdown(f"**Advisory for {crop} in {primary_region}:** :{color}[{advice}]")
st.caption("Rule-based for MVP (trend + slope). Week 3 plan: replace/augment with a Gemini prompt for natural-language reasoning. This is advisory only, not financial advice.")

# ---------------------------------------------------------------------------
# 8. MOCK NEWS / ALERTS FEED
# ---------------------------------------------------------------------------
st.subheader("News & alerts (mock)")
mock_news = [
    "⚠️ Early blight reported in potato crops near Okara — regional supply may tighten.",
    "🌧️ Heavy rains forecast in Punjab next week — possible transport delays to mandis.",
    "📈 Eid demand expected to push meat & produce prices up over the next 10 days.",
]
for n in mock_news:
    st.write("-", n)

# ---------------------------------------------------------------------------
# 9. EXPORT
# ---------------------------------------------------------------------------
st.subheader("Export data")
csv = filtered.to_csv(index=False).encode("utf-8")
st.download_button("Download filtered data as CSV", csv, file_name=f"{crop}_prices.csv", mime="text/csv")
