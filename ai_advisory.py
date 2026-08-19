"""
ai_advisory.py
--------------
Turns price stats you already calculate (current price, 7-day % change,
30-day % change) into a short natural-language insight using the Gemini API
— this is the Week 3 requirement from your brief:

    "Prices for potato in Lahore rising 8% this week —
     possible early blight supply drop?"

WHY A SEPARATE FILE?
Keeping this outside app.py means you can test and tune the prompt here,
independently, without restarting Streamlit every time. Run this file
directly to try it on some example scenarios:

    python ai_advisory.py

Once you're happy with the wording, app.py imports get_ai_insight() from
here and calls it with real numbers from the dashboard.

SETUP:
1. Get a free API key from https://aistudio.google.com (Google AI Studio)
2. Either set it as an environment variable:
     Windows (PowerShell):  $env:GEMINI_API_KEY = "your-key-here"
   ...or paste it into the sidebar text box in the dashboard itself
   (see app.py) — either way works, the env var is just more permanent.
"""

import os
import requests

GEMINI_MODEL = "gemini-2.5-flash-lite"  # current fast/cheap model as of mid-2026
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def build_prompt(crop, region, current_price, chg_7d, chg_30d):
    """
    Builds the text prompt sent to Gemini. Kept as its own function so you
    can tweak the wording easily while testing.
    """
    chg_7d_text = f"{chg_7d:+.1f}%" if chg_7d is not None else "not enough data"
    chg_30d_text = f"{chg_30d:+.1f}%" if chg_30d is not None else "not enough data"

    return f"""You are an agricultural market analyst writing a ONE-SENTENCE insight
for a farmer/trader dashboard in Pakistan. Be concise and cautious — you are
guessing at a plausible reason for a price move, not stating a confirmed fact.

Crop: {crop}
Region/mandi: {region}
Current price: PKR {current_price:,.0f} per 40kg
7-day price change: {chg_7d_text}
30-day price change: {chg_30d_text}

Write ONE short sentence (max ~20 words) in this style:
"Prices for potato in Lahore rising 8% this week — possible early blight supply drop?"

Rules:
- Use hedging language ("possible", "likely", "may reflect") — never state the cause as fact.
- If both changes are small/flat, say prices look stable — don't invent a dramatic reason.
- Do not repeat the exact numbers back verbatim; refer to them naturally (e.g. "rising" / "falling slightly").
- Output ONLY the one sentence, no preamble, no quotation marks.
"""


def resolve_api_key(api_key=None):
    """Finds a Gemini API key from (in order): the argument passed in, the
    GEMINI_API_KEY environment variable (local `setx` setup), or Streamlit
    Cloud's Secrets manager. Returns None if no key is found anywhere."""
    if api_key:
        return api_key
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return api_key
    # Fallback for Streamlit Cloud deployment: a local `setx` environment
    # variable only exists on YOUR machine, not on the cloud server. On
    # Streamlit Cloud, secrets are set via the app's "Secrets" settings
    # panel instead, and read through st.secrets. Importing streamlit here
    # (rather than at the top of the file) keeps this module usable
    # standalone (`python ai_advisory.py`) even without streamlit running.
    try:
        import streamlit as st
        return st.secrets.get("GEMINI_API_KEY")
    except Exception:
        return None


def call_gemini_raw(prompt, api_key=None, timeout=10):
    """
    Generic Gemini call: sends any prompt, returns the raw text response.
    Used both by get_ai_insight (price insights) and farmer_assistant.py
    (translation) — one shared, tested code path for talking to Gemini,
    rather than two separate implementations that could drift apart.
    Returns None on any failure (no key, network error, bad response).
    """
    api_key = resolve_api_key(api_key)
    if not api_key:
        return None

    try:
        response = requests.post(
            GEMINI_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"[ai_advisory] Gemini call failed: {e}")
        return None


def get_ai_insight(crop, region, current_price, chg_7d, chg_30d, api_key=None, timeout=10):
    """
    Calls the Gemini API and returns a one-sentence insight string.
    Returns None if it fails for any reason (no key, network error, bad
    response, etc.) — the caller (app.py) should fall back to the
    rule-based advisory when this returns None, rather than crashing.
    """
    prompt = build_prompt(crop, region, current_price, chg_7d, chg_30d)
    return call_gemini_raw(prompt, api_key=api_key, timeout=timeout)


# ---------------------------------------------------------------------------
# Standalone test — run this file directly to try a few scenarios and see
# what Gemini returns, before wiring it into the dashboard.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_scenarios = [
        {"crop": "Potato", "region": "Lahore", "current_price": 2400, "chg_7d": 8.2, "chg_30d": 15.0},
        {"crop": "Tomato", "region": "Multan", "current_price": 1800, "chg_7d": -12.5, "chg_30d": -20.0},
        {"crop": "Wheat", "region": "Faisalabad", "current_price": 2850, "chg_7d": 0.4, "chg_30d": 1.1},
    ]

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("No GEMINI_API_KEY environment variable found.")
        print("Set it first, e.g. (PowerShell):  $env:GEMINI_API_KEY = \"your-key-here\"")
        print("Or paste it below just for this test run:")
        api_key = input("API key (leave blank to cancel): ").strip() or None

    if api_key:
        for s in test_scenarios:
            insight = get_ai_insight(**s, api_key=api_key)
            print(f"\n{s['crop']} in {s['region']} (7d: {s['chg_7d']:+.1f}%, 30d: {s['chg_30d']:+.1f}%):")
            print(f"  -> {insight if insight else '[FAILED — check API key / connection]'}")
