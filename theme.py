"""
theme.py
--------
Single source of truth for theme colors. Used by BOTH:
  - app.py, to build the CSS variable overrides for light/dark mode
  - dashboard_page.py, to theme the Plotly charts (background, gridlines,
    font color, line/bar colors)

WHY ONE SHARED FILE?
Before this, app.py hardcoded a "dark_vars" CSS string, and dashboard_page.py
separately hardcoded a plotly color list — two color definitions for the
same app that could (and did) drift apart, e.g. dark mode's CSS background
being dark green while every chart stayed plotly-default white. Same
reasoning as price_utils.py: one shared source, not two that can disagree.

Each theme also ships a small `palette` — a curated, on-brand set of colors
(greens/oranges for light, lighter high-contrast tints for dark) used for
chart lines/bars instead of Plotly's generic default qualitative palette
(which clashes with the orange + dark-green branding and has poor contrast
on a dark background).
"""

THEMES = {
    "light": {
        # CSS variables (mirrors styles.css defaults)
        "bg": "#FFF8E7",
        "text": "#1B5E20",
        "card": "#FFFFFF",
        "input_bg": "#FFF3E0",
        "input_text": "#1B5E20",
        "placeholder": "#558B2F",
        "btn_bg": "#EF6C00",
        "btn_border": "#E65100",
        "btn_hover": "#F57C00",
        "sidebar_bg": "#1B5E20",
        "sidebar_text": "#FFF8E7",
        "accent": "#EF6C00",
        "heading": "#1B5E20",
        "alert_bg": "#FFF3E0",
        "alert_text": "#1B5E20",
        "dark_green": "#1B5E20",
        "orange": "#EF6C00",
        "light_orange": "#FFB74D",
        "sky_blue": "#EF6C00",
        "light_green": "#FFB74D",

        # Plotly-specific
        "paper_bg": "#FFF8E7",   # matches --bg, so chart blends into the page
        "plot_bg": "#FFFFFF",    # matches --card, gives the plotting area a subtle card feel
        "grid": "#E6DCC0",       # soft warm gridline, visible but not loud on cream bg
        "palette": [
            "#1B5E20", "#EF6C00", "#2E7D32", "#B5651D", "#558B2F",
            "#F57C00", "#00695C", "#AD1457", "#33691E", "#5D4037",
        ],
    },
    "dark": {
        # CSS variables (mirrors app.py's old dark_vars, now generated here)
        "bg": "#0D1F12",
        "text": "#E8F5E9",
        "card": "#1B3A24",
        "input_bg": "#1B3A24",
        "input_text": "#E8F5E9",
        "placeholder": "#A5D6A7",
        "btn_bg": "#EF6C00",
        "btn_border": "#FF9800",
        "btn_hover": "#FF9800",
        "sidebar_bg": "#06140A",
        "sidebar_text": "#E8F5E9",
        "accent": "#FF9800",
        "heading": "#FFB74D",
        "alert_bg": "#1B3A24",
        "alert_text": "#E8F5E9",
        "dark_green": "#A5D6A7",
        "orange": "#FF9800",
        "light_orange": "#FFB74D",
        "sky_blue": "#FF9800",
        "light_green": "#FFB74D",

        # Plotly-specific
        "paper_bg": "#0D1F12",   # matches --bg
        "plot_bg": "#16281B",    # a touch lighter than --bg, like --card, so the plot area reads as a surface
        "grid": "#2E4A36",       # muted green gridline, visible on the dark plot area without glowing
        "palette": [
            "#FFB74D", "#81C784", "#4FC3F7", "#FF8A65", "#BA68C8",
            "#DCE775", "#4DB6AC", "#F06292", "#90A4AE", "#FFD54F",
        ],
    },
}


def get_theme(theme_name):
    """Returns the theme dict for 'light' or 'dark', defaulting to light for
    any unrecognized value (e.g. before session_state has been set)."""
    return THEMES.get(theme_name, THEMES["light"])
