"""
app.py
------
Agri Market Price Trends, Forecasting & Sell Advisory Dashboard.

This file is now the orchestrator only: page config, mobile CSS, language
toggle, auth gate, and shared data loading. The actual page content lives
in separate files (dashboard_page.py, ask_page.py, account_page.py),
switched between using Streamlit's built-in multi-page navigation
(st.navigation) — this replaces the old single giant script, which had
become cluttered as more features were added.

Run with:  streamlit run app.py
(Make sure real_mandi_prices.csv exists — run combine_real_data.py first,
or set DATA_URL for auto-download on deployment — see DEPLOYMENT_GUIDE.md)
"""

import os
import requests
import streamlit as st
import pandas as pd
from auth import create_user, authenticate, get_user_tier, set_user_tier
from translations import t
import dashboard_page
import ask_page
import account_page

st.set_page_config(page_title="Agri Price Advisory", layout="wide", page_icon="🌾")

# ---------------------------------------------------------------------------
# MOBILE RESPONSIVENESS (Week 4 requirement)
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@media (max-width: 640px) {
    [data-testid="stHorizontalBlock"] { flex-direction: column !important; }
    [data-testid="stMetricValue"] { font-size: 1.3rem !important; }
    .block-container { padding: 1rem 0.8rem !important; }
    h1 { font-size: 1.5rem !important; }
    h2, h3 { font-size: 1.15rem !important; }
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# LANGUAGE TOGGLE (English / Urdu)
# ---------------------------------------------------------------------------
# Set BEFORE the auth gate so a farmer can switch to Urdu before even
# logging in — the login screen itself should be readable in either
# language, not just the dashboard after login.
if "lang" not in st.session_state:
    st.session_state.lang = "en"

lang_choice = st.sidebar.radio(
    t("language_label"), options=["en", "ur"],
    format_func=lambda x: "English" if x == "en" else "اردو",
    horizontal=True,
    index=0 if st.session_state.lang == "en" else 1,
    key="lang_radio",
)
st.session_state.lang = lang_choice

# Urdu is a right-to-left script — flip text alignment when Urdu is active
# so it reads naturally instead of left-aligned Urdu text (which looks wrong).
if st.session_state.lang == "ur":
    st.markdown("""
    <style>
    .stMarkdown, .stText, p, h1, h2, h3, .stCaption { direction: rtl; text-align: right; }
    </style>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# AUTH GATE
# ---------------------------------------------------------------------------
if "username" not in st.session_state:
    st.session_state.username = None

if st.session_state.username is None:
    st.title(t("login_title"))

    tab_login, tab_signup = st.tabs([t("login_tab"), t("signup_tab")])

    with tab_login:
        with st.form("login_form"):
            login_user = st.text_input(t("username"))
            login_pass = st.text_input(t("password"), type="password")
            login_submitted = st.form_submit_button(t("login_button"))
            if login_submitted:
                ok, msg = authenticate(login_user, login_pass)
                if ok:
                    st.session_state.username = login_user.strip()
                    st.rerun()
                else:
                    st.error(msg)

    with tab_signup:
        with st.form("signup_form"):
            signup_user = st.text_input(t("username"))
            signup_pass = st.text_input(t("password") + " (min. 6 characters)", type="password")
            signup_submitted = st.form_submit_button(t("signup_button"))
            if signup_submitted:
                ok, msg = create_user(signup_user, signup_pass)
                if ok:
                    st.success(f"{msg}")
                else:
                    st.error(msg)

    st.stop()

# ---------------------------------------------------------------------------
# LOGGED IN: sidebar status + tier controls (shown on every page)
# ---------------------------------------------------------------------------
user_tier = get_user_tier(st.session_state.username)
is_premium = (user_tier == "premium")

st.sidebar.success(f"{t('logged_in_as')} **{st.session_state.username}** ({t('tier_premium') if is_premium else t('tier_free')})")
if st.sidebar.button(t("logout")):
    st.session_state.username = None
    st.rerun()

if not is_premium:
    if st.sidebar.button(t("upgrade")):
        set_user_tier(st.session_state.username, "premium")
        st.rerun()
else:
    if st.sidebar.button(t("downgrade")):
        set_user_tier(st.session_state.username, "free")
        st.rerun()

# ---------------------------------------------------------------------------
# SHARED DATA LOADING (used by all pages)
# ---------------------------------------------------------------------------
DATA_FILE = "real_mandi_prices.csv"


def ensure_data_file():
    if os.path.exists(DATA_FILE):
        return
    data_url = None
    try:
        data_url = st.secrets.get("DATA_URL")
    except Exception:
        pass
    data_url = data_url or os.environ.get("DATA_URL")
    if not data_url:
        st.error(f"'{DATA_FILE}' not found and no DATA_URL is configured. See DEPLOYMENT_GUIDE.md.")
        st.stop()
    with st.spinner("Downloading price dataset (first run only)..."):
        response = requests.get(data_url, timeout=60)
        response.raise_for_status()
        with open(DATA_FILE, "wb") as f:
            f.write(response.content)


ensure_data_file()


@st.cache_data
def load_data():
    df = pd.read_csv(DATA_FILE, parse_dates=["Date"])
    return df.rename(columns={"City": "region", "Date": "date", "Crop": "crop", "Price": "price_pkr_per_40kg"})


df_base = load_data()

# ---------------------------------------------------------------------------
# NAVIGATION (Week 6 polish: split single cluttered page into three)
# ---------------------------------------------------------------------------
# NOTE: st.Page infers each page's URL from the function's name — using
# lambdas here would give every page the same name ("<lambda>"), causing a
# "URL pathnames must be unique" crash. Named wrapper functions avoid that.
def _render_dashboard():
    dashboard_page.render(df_base, is_premium, st.session_state.username)


def _render_ask():
    ask_page.render(df_base)


def _render_account():
    account_page.render(st.session_state.username, is_premium)


page_dashboard = st.Page(_render_dashboard, title=t("nav_dashboard"), icon="📊")
page_ask = st.Page(_render_ask, title=t("nav_ask"), icon="💬")
page_account = st.Page(_render_account, title=t("nav_account"), icon="⚙️")

pg = st.navigation([page_dashboard, page_ask, page_account])
pg.run()
