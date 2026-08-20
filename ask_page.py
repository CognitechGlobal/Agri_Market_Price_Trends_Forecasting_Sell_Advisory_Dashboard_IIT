"""
ask_page.py
-----------
The natural-language Q&A page — a farmer types a question in English or
Urdu (e.g. "what is the price of wheat" or "گندم کی قیمت کیا ہے") and gets
an answer back in the same language, using price_utils under the hood so
the answer matches what the Dashboard page shows for the same crop.
"""

import streamlit as st
from farmer_assistant import answer_query
from translations import t


def render(df):
    st.title(t("ask_title"))
    st.caption(t("ask_subtitle"))

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    with st.form("ask_form", clear_on_submit=True):
        query = st.text_input(t("ask_button"), placeholder=t("ask_placeholder"), label_visibility="collapsed")
        submitted = st.form_submit_button(t("ask_button"))

    if submitted and query.strip():
        # Use whatever regions are already selected on the Dashboard page as
        # a hint for which region to check first (keeps answers consistent
        # with what the farmer's already been looking at), falling back to
        # searching all regions if none are selected yet.
        regions_hint = st.session_state.get("regions_select", [])
        with st.spinner("..."):
            result = answer_query(query.strip(), df, regions_hint)

        st.session_state.chat_history.append({"query": query.strip(), "result": result})

    # Show conversation history, most recent first
    for entry in reversed(st.session_state.chat_history):
        with st.chat_message("user"):
            st.write(entry["query"])
        with st.chat_message("assistant"):
            r = entry["result"]
            if r["error"]:
                st.warning(r["error"])
            else:
                st.write(r["answer"])
                st.caption(f"Matched crop: {r['matched_crop']}")

    if not st.session_state.chat_history:
        st.info(
            "Try asking something like:\n"
            "- \"What is the price of apple?\"\n"
            "- \"آم کی قیمت کیا ہے؟\" (What is the price of mango?)\n"
            "- \"Should I sell my garlic now?\""
        )
