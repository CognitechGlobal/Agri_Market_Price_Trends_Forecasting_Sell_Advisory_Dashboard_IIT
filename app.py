"""
app.py
------
Agri Market Price Trends, Forecasting & Sell Advisory Dashboard (MVP - Week 1-2)

Covers the MVP must-haves:
  1. Filters: crop, region/mandi, date range
  2. Current price + 7/30-day trend charts (interactive, Plotly)
  3. Simple forecasting: moving-average + linear regression projection
  4. Rule-based sell advisory (placeholder for the Gemini layer later)
  5. Cross-mandi comparison
  6. Mock news/alerts feed
  7. CSV export
  8. Data ingestion: CSV upload + manual entry (Week 2)

Run with:  streamlit run app.py
(Make sure real_mandi_prices.csv exists — run combine_real_data.py first,
or generate_mock_data.py if you want to fall back to mock data.)
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import timedelta
from io import BytesIO
from fpdf import FPDF
from ai_advisory import get_ai_insight

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

df_base = load_data()

# ---------------------------------------------------------------------------
# 1a. PDF REPORT BUILDER (Week 3 "polish... export" requirement)
# ---------------------------------------------------------------------------
def build_pdf_report(crop, region, latest_price, chg_7d, chg_30d, advice, ai_insight):
    """Builds a simple one-page PDF summary and returns it as bytes, ready
    for st.download_button. Kept plain (no charts embedded) to stay fast
    and dependency-light for the MVP — a good Week 6 polish item would be
    embedding the actual chart image too."""
    from fpdf.enums import XPos, YPos

    def safe_text(s):
        """fpdf2's built-in fonts only support latin-1. AI-generated text
        can contain smart quotes/em-dashes that would crash the PDF build,
        so replace anything unsupported instead of failing."""
        return s.encode("latin-1", errors="replace").decode("latin-1")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Agri Market Price Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 8, f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"{crop} - {region}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Current price: PKR {latest_price:,.0f} per 40kg", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 8, f"7-day change: {f'{chg_7d:+.1f}%' if chg_7d is not None else 'N/A'}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 8, f"30-day change: {f'{chg_30d:+.1f}%' if chg_30d is not None else 'N/A'}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Sell advisory:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 7, safe_text(advice))
    pdf.ln(2)

    if ai_insight:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "AI insight:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 7, safe_text(ai_insight))

    pdf.ln(5)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 5, "This is an MVP demo report. Data may be illustrative. Advisory is not financial advice.")

    return bytes(pdf.output())

# ---------------------------------------------------------------------------
# 1b. DATA INGESTION (Week 2 requirement: upload CSV or manual entry)
# ---------------------------------------------------------------------------
# Newly added rows live in session_state so they persist while you use the
# app (across filter changes / reruns) without touching the underlying
# real_mandi_prices.csv file until you explicitly choose to save them.
if "extra_data" not in st.session_state:
    st.session_state.extra_data = pd.DataFrame(
        columns=["region", "date", "crop", "price_pkr_per_40kg"]
    )

with st.sidebar.expander("➕ Add data (upload or manual entry)"):
    tab_upload, tab_manual = st.tabs(["Upload CSV", "Manual entry"])

    # --- Upload CSV ---
    with tab_upload:
        st.caption("CSV must have columns: City, Date, Crop, Price (same format as the real dataset).")
        uploaded_file = st.file_uploader("Choose a CSV file", type="csv", key="csv_uploader")
        if uploaded_file is not None:
            try:
                new_df = pd.read_csv(uploaded_file)
                required_cols = {"City", "Date", "Crop", "Price"}
                if not required_cols.issubset(set(new_df.columns)):
                    st.error(f"Missing required columns. Found: {list(new_df.columns)}. Need: {sorted(required_cols)}")
                else:
                    new_df = new_df.rename(columns={
                        "City": "region", "Date": "date", "Crop": "crop", "Price": "price_pkr_per_40kg",
                    })
                    new_df["date"] = pd.to_datetime(new_df["date"], errors="coerce")
                    new_df = new_df.dropna(subset=["region", "date", "crop", "price_pkr_per_40kg"])
                    new_df = new_df[new_df["price_pkr_per_40kg"] > 0]

                    if st.button(f"Add {len(new_df)} rows to dashboard", key="confirm_upload"):
                        st.session_state.extra_data = pd.concat(
                            [st.session_state.extra_data, new_df], ignore_index=True
                        )
                        st.success(f"Added {len(new_df)} rows. Filters below now include this data.")
            except Exception as e:
                st.error(f"Couldn't read that file: {e}")

    # --- Manual entry ---
    with tab_manual:
        with st.form("manual_entry_form", clear_on_submit=True):
            m_crop = st.text_input("Crop name", placeholder="e.g. Wheat")
            m_region = st.text_input("City / mandi", placeholder="e.g. Lahore")
            m_date = st.date_input("Date", value=df_base["date"].max().date())
            m_price = st.number_input("Price (PKR per 40kg)", min_value=0.0, step=10.0)
            submitted = st.form_submit_button("Add entry")

            if submitted:
                if not m_crop or not m_region or m_price <= 0:
                    st.error("Please fill in crop, city, and a price greater than 0.")
                else:
                    new_row = pd.DataFrame([{
                        "region": m_region.strip(), "date": pd.Timestamp(m_date),
                        "crop": m_crop.strip(), "price_pkr_per_40kg": m_price,
                    }])
                    st.session_state.extra_data = pd.concat(
                        [st.session_state.extra_data, new_row], ignore_index=True
                    )
                    st.success(f"Added: {m_crop} in {m_region} on {m_date} — PKR {m_price:,.0f}")

    if len(st.session_state.extra_data) > 0:
        st.caption(f"📌 {len(st.session_state.extra_data)} row(s) added this session (not yet saved to file).")
        if st.button("💾 Save all added data to real_mandi_prices.csv"):
            combined = pd.concat([df_base, st.session_state.extra_data], ignore_index=True)
            combined = combined.rename(columns={
                "region": "City", "date": "Date", "crop": "Crop", "price_pkr_per_40kg": "Price",
            })
            combined.to_csv("real_mandi_prices.csv", index=False)
            st.success("Saved! Restart the app to reload from the updated file.")
        if st.button("🗑️ Clear added data (this session only)"):
            st.session_state.extra_data = pd.DataFrame(columns=["region", "date", "crop", "price_pkr_per_40kg"])
            st.rerun()

# Merge base data with anything added this session — everything below (filters,
# charts, forecast, advisory) automatically sees the combined dataset.
df = pd.concat([df_base, st.session_state.extra_data], ignore_index=True)

# IMPORTANT: pd.concat silently converts date/price to generic "object" dtype
# when merging with an empty (or freshly-typed) session_state frame. That
# breaks date comparisons, sorting, and the forecast math further down —
# so force the correct types back explicitly right after merging.
df["date"] = pd.to_datetime(df["date"])
df["price_pkr_per_40kg"] = pd.to_numeric(df["price_pkr_per_40kg"])

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
# 4. TREND CHART (line, multi-region, distinct colors per region + direction in legend)
# ---------------------------------------------------------------------------
st.subheader(f"{crop} price trend")

# FIX: the earlier version colored every line green/red by direction, but
# that meant all "rising" cities looked identical and all "falling" cities
# looked identical — you couldn't tell WHICH city was which anymore.
# Now: each region keeps its own distinct color (so you can always match a
# line to its legend entry), and direction is shown instead as an
# up/down arrow + % change appended to the legend label itself.
DISTINCT_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]

fig = go.Figure()
for i, r in enumerate(regions):
    r_df = filtered[filtered["region"] == r].sort_values("date")
    color = DISTINCT_COLORS[i % len(DISTINCT_COLORS)]

    if len(r_df) < 2:
        label = f"{r} (not enough data)"
    else:
        start_p, end_p = r_df["price_pkr_per_40kg"].iloc[0], r_df["price_pkr_per_40kg"].iloc[-1]
        pct = (end_p - start_p) / start_p * 100
        arrow = "▲" if pct >= 0 else "▼"
        label = f"{r} {arrow} {pct:+.1f}%"

    fig.add_trace(go.Scatter(
        x=r_df["date"], y=r_df["price_pkr_per_40kg"],
        mode="lines", name=label, line=dict(color=color, width=2.5),
    ))
fig.update_layout(
    yaxis_title="PKR per 40kg", xaxis_title="Date",
    hovermode="x unified", height=420,
)
st.plotly_chart(fig, use_container_width=True)
st.caption("Each city keeps its own color. The legend shows ▲/▼ and % change over the selected date range for quick comparison.")

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
st.caption("Rule-based (trend + slope) advisory. This is advisory only, not financial advice.")

# ---------------------------------------------------------------------------
# 7b. AI-GENERATED NATURAL LANGUAGE INSIGHT (Week 3: Gemini layer)
# ---------------------------------------------------------------------------
st.markdown("**AI insight** (experimental)")

gemini_key = st.sidebar.text_input(
    "Gemini API key (optional, for AI insights)", type="password",
    help="Get a free key at https://aistudio.google.com — leave blank to skip AI insights.",
)

ai_insight = get_ai_insight(crop, primary_region, latest_price, chg_7d, chg_30d, api_key=gemini_key)

if ai_insight:
    st.info(f"🤖 {ai_insight}")
else:
    st.caption(
        "No AI insight available — paste a Gemini API key in the sidebar to enable this "
        "(get a free one at aistudio.google.com), or the call may have failed. "
        "The rule-based advisory above still works either way."
    )

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

col_csv, col_pdf = st.columns(2)

csv = filtered.to_csv(index=False).encode("utf-8")
col_csv.download_button("📄 Download filtered data as CSV", csv, file_name=f"{crop}_prices.csv", mime="text/csv")

# UPGRADE (Week 3 "polish... export"): one-click PDF summary report — crop,
# region, current stats, advisory, and AI insight, for records/printing.
pdf_bytes = build_pdf_report(
    crop=crop, region=primary_region, latest_price=latest_price,
    chg_7d=chg_7d, chg_30d=chg_30d, advice=advice, ai_insight=ai_insight,
)
col_pdf.download_button(
    "📑 Download PDF summary report", pdf_bytes,
    file_name=f"{crop}_{primary_region}_report.pdf", mime="application/pdf",
)
