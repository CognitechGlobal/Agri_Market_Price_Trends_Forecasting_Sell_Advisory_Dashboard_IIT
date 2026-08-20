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

    st.subheader(t("account_tier"))
    tier_label = t("tier_premium_label") if is_premium else t("tier_free_label")
    st.write(t("account_tier_status").format(tier=tier_label))
    if not is_premium:
        st.caption(t("account_upgrade_hint"))

    st.subheader(t("account_saved"))
    if not is_premium:
        st.caption(t("account_saved_locked"))
        return

    saved = get_saved_dashboards(username)
    if not saved:
        st.write(t("account_saved_empty"))
        return

    for name, view in saved.items():
        with st.expander(name):
            st.write(f"**{t('account_crop')}:** {view['crop']}")
            st.write(f"**{t('account_regions')}:** {', '.join(view['regions'])}")
            st.write(f"**{t('account_date_range')}:** {view['start_date']} to {view['end_date']}")
            if st.button(t("account_delete"), key=f"delete_{name}"):
                delete_saved_dashboard(username, name)
                st.rerun()
