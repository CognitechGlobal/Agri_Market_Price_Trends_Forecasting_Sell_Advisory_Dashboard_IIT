"""
account_page.py
----------------
Account overview: tier status and saved dashboards list. The actual
upgrade/downgrade buttons live in the sidebar (visible on every page, since
they're a global account action), but this page gives a fuller view.
"""

import streamlit as st
from auth import get_saved_dashboards, delete_saved_dashboard
from translations import t


def render(username, is_premium):
    st.title(t("nav_account"))

    st.subheader("Tier")
    st.write(f"You are currently on the **{'Premium' if is_premium else 'Free'}** tier.")
    if not is_premium:
        st.caption("Upgrade from the sidebar to unlock full price history, AI insights, PDF export, and saved dashboards.")

    st.subheader("Saved dashboards")
    if not is_premium:
        st.caption("🔒 Saved dashboards are a Premium feature.")
        return

    saved = get_saved_dashboards(username)
    if not saved:
        st.write("You haven't saved any dashboard views yet. Save one from the Dashboard page's sidebar.")
        return

    for name, view in saved.items():
        with st.expander(name):
            st.write(f"**Crop:** {view['crop']}")
            st.write(f"**Regions:** {', '.join(view['regions'])}")
            st.write(f"**Date range:** {view['start_date']} to {view['end_date']}")
            if st.button("Delete", key=f"delete_{name}"):
                delete_saved_dashboard(username, name)
                st.rerun()
