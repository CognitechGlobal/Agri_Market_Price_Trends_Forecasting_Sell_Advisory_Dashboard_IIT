"""
dashboard_page.py
------------------
The main charts/filters page — moved out of app.py as part of splitting the
single-page app into a proper multi-page structure (Dashboard / Ask / Account).

Uses price_utils for all price calculations, so the stats shown here are
guaranteed to match what the "Ask About a Crop" page reports for the same
crop — one shared calculation path, not two that could drift apart.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import timedelta
from fpdf import FPDF
from ai_advisory import get_ai_insight
from auth import save_dashboard, get_saved_dashboards, delete_saved_dashboard
from price_utils import find_valid_region, get_crop_stats, get_forecast, rule_based_advice
from translations import t

FREE_TIER_LOOKBACK_DAYS = 30


def build_pdf_report(crop, region, latest_price, chg_7d, chg_30d, advice, ai_insight):
    """Builds a simple one-page PDF summary and returns it as bytes."""
    from fpdf.enums import XPos, YPos

    def safe_text(s):
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


def render(df_base, is_premium, username):
    # --- Data ingestion (Week 2): CSV upload + manual entry ---
    if "extra_data" not in st.session_state:
        st.session_state.extra_data = pd.DataFrame(columns=["region", "date", "crop", "price_pkr_per_40kg"])

    with st.sidebar.expander("➕ Add data (upload or manual entry)"):
        tab_upload, tab_manual = st.tabs(["Upload CSV", "Manual entry"])

        with tab_upload:
            st.caption("CSV must have columns: City, Date, Crop, Price.")
            uploaded_file = st.file_uploader("Choose a CSV file", type="csv", key="csv_uploader")
            if uploaded_file is not None:
                try:
                    new_df = pd.read_csv(uploaded_file)
                    required_cols = {"City", "Date", "Crop", "Price"}
                    if not required_cols.issubset(set(new_df.columns)):
                        st.error(f"Missing required columns. Found: {list(new_df.columns)}. Need: {sorted(required_cols)}")
                    else:
                        new_df = new_df.rename(columns={"City": "region", "Date": "date", "Crop": "crop", "Price": "price_pkr_per_40kg"})
                        new_df["date"] = pd.to_datetime(new_df["date"], errors="coerce")
                        new_df = new_df.dropna(subset=["region", "date", "crop", "price_pkr_per_40kg"])
                        new_df = new_df[new_df["price_pkr_per_40kg"] > 0]
                        if st.button(f"Add {len(new_df)} rows to dashboard", key="confirm_upload"):
                            st.session_state.extra_data = pd.concat([st.session_state.extra_data, new_df], ignore_index=True)
                            st.success(f"Added {len(new_df)} rows. Filters below now include this data.")
                except Exception as e:
                    st.error(f"Couldn't read that file: {e}")

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
                        new_row = pd.DataFrame([{"region": m_region.strip(), "date": pd.Timestamp(m_date), "crop": m_crop.strip(), "price_pkr_per_40kg": m_price}])
                        st.session_state.extra_data = pd.concat([st.session_state.extra_data, new_row], ignore_index=True)
                        st.success(f"Added: {m_crop} in {m_region} on {m_date} — PKR {m_price:,.0f}")

        if len(st.session_state.extra_data) > 0:
            st.caption(f"📌 {len(st.session_state.extra_data)} row(s) added this session (not yet saved to file).")
            if st.button("💾 Save all added data to real_mandi_prices.csv"):
                combined = pd.concat([df_base, st.session_state.extra_data], ignore_index=True)
                combined = combined.rename(columns={"region": "City", "date": "Date", "crop": "Crop", "price_pkr_per_40kg": "Price"})
                combined.to_csv("real_mandi_prices.csv", index=False)
                st.success("Saved! Restart the app to reload from the updated file.")
            if st.button("🗑️ Clear added data (this session only)"):
                st.session_state.extra_data = pd.DataFrame(columns=["region", "date", "crop", "price_pkr_per_40kg"])
                st.rerun()

    df = pd.concat([df_base, st.session_state.extra_data], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["price_pkr_per_40kg"] = pd.to_numeric(df["price_pkr_per_40kg"])

    # --- Filters ---
    st.sidebar.title(t("filters"))

    min_date, max_date = df["date"].min(), df["date"].max()
    all_regions = sorted(df["region"].unique())

    if is_premium:
        allowed_min_date = min_date.date()
    else:
        allowed_min_date = max(min_date.date(), (max_date - timedelta(days=FREE_TIER_LOOKBACK_DAYS)).date())

    if "crop_select" not in st.session_state:
        st.session_state["crop_select"] = sorted(df["crop"].unique())[0]
    if "regions_select" not in st.session_state:
        st.session_state["regions_select"] = all_regions[:3]
    if "start_date_input" not in st.session_state:
        st.session_state["start_date_input"] = (max_date - timedelta(days=FREE_TIER_LOOKBACK_DAYS)).date()
    if "end_date_input" not in st.session_state:
        st.session_state["end_date_input"] = max_date.date()

    if not is_premium and st.session_state["start_date_input"] < allowed_min_date:
        st.session_state["start_date_input"] = allowed_min_date

    if not is_premium:
        st.sidebar.caption("📂 Saved dashboards are a Premium feature — upgrade to unlock.")
    else:
        my_saved = get_saved_dashboards(username)
        if my_saved:
            with st.sidebar.expander("📂 Load a saved dashboard"):
                pick = st.selectbox("Saved views", ["-- none --"] + list(my_saved.keys()))
                col_load, col_del = st.columns(2)
                if col_load.button("Load", disabled=(pick == "-- none --")):
                    saved = my_saved[pick]
                    st.session_state["crop_select"] = saved["crop"]
                    st.session_state["regions_select"] = saved["regions"]
                    st.session_state["start_date_input"] = pd.Timestamp(saved["start_date"]).date()
                    st.session_state["end_date_input"] = pd.Timestamp(saved["end_date"]).date()
                    st.rerun()
                if col_del.button("Delete", disabled=(pick == "-- none --")):
                    delete_saved_dashboard(username, pick)
                    st.rerun()

    crop = st.sidebar.selectbox(t("crop"), sorted(df["crop"].unique()), key="crop_select")
    regions = st.sidebar.multiselect(t("region"), all_regions, key="regions_select")

    if not is_premium:
        st.sidebar.caption(f"🔒 Free tier: limited to the last {FREE_TIER_LOOKBACK_DAYS} days. Upgrade for full history.")

    col_start, col_end = st.sidebar.columns(2)
    start_date = col_start.date_input(t("from_date"), min_value=allowed_min_date, max_value=max_date.date(), key="start_date_input")
    end_date = col_end.date_input(t("to_date"), min_value=allowed_min_date, max_value=max_date.date(), key="end_date_input")

    if start_date > end_date:
        st.sidebar.error("'From' date must be before 'To' date.")
        st.stop()

    date_range = (pd.Timestamp(start_date), pd.Timestamp(end_date))

    if is_premium:
        with st.sidebar.expander("💾 Save current view"):
            save_name = st.text_input("Name this view", placeholder="e.g. My Potato Watch")
            if st.button("Save"):
                if not save_name.strip():
                    st.error("Give it a name first.")
                else:
                    ok, msg = save_dashboard(username, save_name.strip(), crop, regions, start_date, end_date)
                    st.success(msg) if ok else st.error(msg)

    if not regions:
        st.warning("Select at least one region from the sidebar.")
        st.stop()

    filtered = df[(df["crop"] == crop) & (df["region"].isin(regions)) & (df["date"] >= date_range[0]) & (df["date"] <= date_range[1])].copy()

    st.title(t("dashboard_title"))
    st.caption(
        f"MVP dashboard — real mandi price data, {df['date'].min().date()} to {df['date'].max().date()}. "
        "Not live/real-time pricing. Advisory is informational only, not financial advice."
    )

    # --- KPI cards (using shared price_utils logic) ---
    valid_regions = [r for r in regions if ((df["crop"] == crop) & (df["region"] == r)).any()]
    if not valid_regions:
        st.warning(f"No price data found for **{crop}** in any of the selected regions. Try picking a different region or crop.")
        st.stop()

    primary_region = valid_regions[0]
    stats = get_crop_stats(df, crop, primary_region)
    latest_price, chg_7d, chg_30d = stats["latest_price"], stats["chg_7d"], stats["chg_30d"]

    col1, col2, col3 = st.columns(3)
    col1.metric(f"{t('current_price')} ({primary_region})", f"PKR {latest_price:,.0f}/40kg")
    col2.metric(t("change_7d"), f"{chg_7d:+.1f}%" if chg_7d is not None else "N/A")
    col3.metric(t("change_30d"), f"{chg_30d:+.1f}%" if chg_30d is not None else "N/A")

    # --- Trend chart ---
    st.subheader(f"{crop} {t('price_trend')}")
    DISTINCT_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
    fig = go.Figure()
    flat_regions = []
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
            if r_df["price_pkr_per_40kg"].std() < (r_df["price_pkr_per_40kg"].mean() * 0.0001):
                flat_regions.append(r)
        fig.add_trace(go.Scatter(x=r_df["date"], y=r_df["price_pkr_per_40kg"], mode="lines", name=label, line=dict(color=color, width=2.5)))
    fig.update_layout(yaxis_title="PKR per 40kg", xaxis_title="Date", hovermode="x unified", height=420)
    st.plotly_chart(fig, width="stretch")
    st.caption("Each city keeps its own color. The legend shows ▲/▼ and % change over the selected date range.")
    if flat_regions:
        st.warning(f"⚠️ Price for **{', '.join(flat_regions)}** shows no change across this date range — a real data characteristic, not a display error.")

    # --- Mandi comparison ---
    st.subheader(f"Current {crop} price by mandi")
    latest_by_region = df[df["crop"] == crop].sort_values("date").groupby("region").tail(1).sort_values("price_pkr_per_40kg")
    fig2 = go.Figure(go.Bar(x=latest_by_region["region"], y=latest_by_region["price_pkr_per_40kg"]))
    fig2.update_layout(yaxis_title="PKR per 40kg", height=350)
    st.plotly_chart(fig2, width="stretch")

    # --- Forecast (using shared price_utils logic) ---
    st.subheader("Simple forecast (7-day moving average + linear regression)")
    hist = stats["hist"]
    recent_slope = stats["recent_slope"]
    future_dates = [hist["date"].iloc[-1] + timedelta(days=i) for i in range(1, 8)]
    future_prices = [hist["ma7"].iloc[-1] + recent_slope * i for i in range(1, 8)]

    forecast = get_forecast(hist)
    if forecast is None:
        st.info(f"Not enough price history for {crop} in {primary_region} to build a forecast yet.")
    else:
        band_width = forecast["resid_std"] * (1 + 0.15 * np.arange(1, 8))
        lr_upper = forecast["prices"] + band_width
        lr_lower = forecast["prices"] - band_width

        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=hist["date"], y=hist["price_pkr_per_40kg"], name="Actual price", mode="lines"))
        fig3.add_trace(go.Scatter(x=hist["date"], y=hist["ma7"], name="7-day MA", mode="lines", line=dict(dash="dot")))
        fig3.add_trace(go.Scatter(x=future_dates, y=future_prices, name="Forecast (moving avg)", mode="lines", line=dict(dash="dash", color="orange")))
        fig3.add_trace(go.Scatter(x=forecast["dates"], y=forecast["prices"], name="Forecast (linear regression)", mode="lines", line=dict(dash="dash", color="purple")))
        fig3.add_trace(go.Scatter(x=forecast["dates"], y=lr_upper, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig3.add_trace(go.Scatter(x=forecast["dates"], y=lr_lower, mode="lines", line=dict(width=0), fill="tonexty", fillcolor="rgba(128,0,128,0.15)", name="Confidence band", hoverinfo="skip"))
        fig3.update_layout(yaxis_title="PKR per 40kg", height=400)
        st.plotly_chart(fig3, width="stretch")
        st.caption("Two forecasting methods shown for comparison. The shaded band widens further out, reflecting more uncertainty.")

    # --- Advisory ---
    st.subheader(t("sell_advisory"))
    advice, color = rule_based_advice(chg_7d, recent_slope)
    st.markdown(f"**Advisory for {crop} in {primary_region}:** :{color}[{advice}]")
    st.caption("Rule-based (trend + slope) advisory. This is advisory only, not financial advice.")

    # --- AI insight (Premium) ---
    st.markdown(f"**{t('ai_insight')}** (experimental)")
    ai_insight = None
    if not is_premium:
        st.caption("🔒 AI insights are a Premium feature. Click '⭐ Upgrade to Premium' in the sidebar to unlock.")
    else:
        ai_insight = get_ai_insight(crop, primary_region, latest_price, chg_7d, chg_30d)
        if ai_insight:
            st.info(f"🤖 {ai_insight}")
        else:
            st.caption("No AI insight available — make sure GEMINI_API_KEY is configured. Rule-based advisory above still works.")

    # --- Mock news ---
    st.subheader("News & alerts (mock)")
    for n in [
        "⚠️ Early blight reported in potato crops near Okara — regional supply may tighten.",
        "🌧️ Heavy rains forecast in Punjab next week — possible transport delays to mandis.",
        "📈 Eid demand expected to push meat & produce prices up over the next 10 days.",
    ]:
        st.write("-", n)

    # --- Export ---
    st.subheader("Export data")
    col_csv, col_pdf = st.columns(2)
    csv = filtered.to_csv(index=False).encode("utf-8")
    col_csv.download_button("📄 Download filtered data as CSV", csv, file_name=f"{crop}_prices.csv", mime="text/csv")
    if is_premium:
        pdf_bytes = build_pdf_report(crop=crop, region=primary_region, latest_price=latest_price, chg_7d=chg_7d, chg_30d=chg_30d, advice=advice, ai_insight=ai_insight)
        col_pdf.download_button("📑 Download PDF summary report", pdf_bytes, file_name=f"{crop}_{primary_region}_report.pdf", mime="application/pdf")
    else:
        col_pdf.caption("🔒 PDF reports are a Premium feature. Upgrade in the sidebar to unlock.")
