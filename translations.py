"""
translations.py
----------------
UI text in English and Urdu, plus a small helper `t()` to look up the right
string based on the current language in st.session_state.

WHY A DICTIONARY, NOT A TRANSLATION LIBRARY FOR THE UI?
UI labels are fixed and few — a dictionary is instant, free, and never fails
(no API call, no network dependency, no risk of a bad machine translation on
a button label). Machine translation (via Gemini) is used separately, only
for the farmer's free-text QUESTIONS and AI-generated insights in
farmer_assistant.py, where the text is genuinely dynamic and can't be
pre-written.
"""

import streamlit as st

TRANSLATIONS = {
    "app_title": {"en": "Agri Price Advisory", "ur": "زرعی قیمت مشاورت"},
    "login_title": {"en": "🌾 Agri Price Advisory — Login", "ur": "🌾 زرعی قیمت مشاورت — لاگ ان"},
    "login_tab": {"en": "Log in", "ur": "لاگ ان"},
    "signup_tab": {"en": "Sign up", "ur": "اکاؤنٹ بنائیں"},
    "username": {"en": "Username", "ur": "یوزر نیم"},
    "password": {"en": "Password", "ur": "پاس ورڈ"},
    "login_button": {"en": "Log in", "ur": "لاگ ان کریں"},
    "signup_button": {"en": "Create account", "ur": "اکاؤنٹ بنائیں"},
    "logout": {"en": "Log out", "ur": "لاگ آؤٹ"},
    "upgrade": {"en": "⭐ Upgrade to Premium (demo)", "ur": "⭐ پریمیم میں اپ گریڈ کریں"},
    "downgrade": {"en": "Downgrade to Free (demo)", "ur": "فری میں واپس جائیں"},
    "logged_in_as": {"en": "Logged in as", "ur": "لاگ ان ہیں بطور"},
    "tier_free": {"en": "free tier", "ur": "فری"},
    "tier_premium": {"en": "premium tier", "ur": "پریمیم"},

    "nav_dashboard": {"en": "📊 Dashboard", "ur": "📊 ڈیش بورڈ"},
    "nav_ask": {"en": "💬 Ask About a Crop", "ur": "💬 فصل کے بارے میں پوچھیں"},
    "nav_account": {"en": "⚙️ Account", "ur": "⚙️ اکاؤنٹ"},

    "filters": {"en": "🌾 Filters", "ur": "🌾 فلٹرز"},
    "crop": {"en": "Crop", "ur": "فصل"},
    "region": {"en": "Region(s) / Mandi", "ur": "شہر / منڈی"},
    "from_date": {"en": "From", "ur": "تاریخ سے"},
    "to_date": {"en": "To", "ur": "تاریخ تک"},

    "dashboard_title": {"en": "Agri Market Price Trends & Sell Advisory", "ur": "زرعی منڈی قیمت رجحانات اور فروخت کا مشورہ"},
    "current_price": {"en": "Current price", "ur": "موجودہ قیمت"},
    "change_7d": {"en": "7-day change", "ur": "7 دن کی تبدیلی"},
    "change_30d": {"en": "30-day change", "ur": "30 دن کی تبدیلی"},
    "price_trend": {"en": "price trend", "ur": "قیمت کا رجحان"},
    "sell_advisory": {"en": "Sell advisory", "ur": "فروخت کا مشورہ"},
    "ai_insight": {"en": "AI insight", "ur": "AI بصیرت"},

    "ask_placeholder": {"en": "e.g. What's the price of mango?", "ur": "مثلاً آم کی قیمت کیا ہے؟"},
    "ask_button": {"en": "Ask", "ur": "پوچھیں"},
    "ask_title": {"en": "Ask About a Crop", "ur": "فصل کے بارے میں پوچھیں"},
    "ask_subtitle": {
        "en": "Type your question in English or Urdu — e.g. \"what is the price of apple\" or \"آم کی قیمت کیا ہے\"",
        "ur": "اپنا سوال اردو یا انگریزی میں لکھیں — مثلاً \"آم کی قیمت کیا ہے\"",
    },

    "language_label": {"en": "Language / زبان", "ur": "Language / زبان"},
}


def t(key):
    """Looks up a UI string in the current language (defaults to English if
    the language isn't set yet, or if the key doesn't exist)."""
    lang = st.session_state.get("lang", "en")
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key  # fail loudly-ish: show the raw key so missing translations are obvious, not blank
    return entry.get(lang, entry.get("en", key))
