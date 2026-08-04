"""Local card-view browser for tracked job postings.

Run with: .venv/bin/streamlit run app/app.py
Reads scripts/store.py's SQLite DB directly — read-only except for the
status field, which cards write back to via a selectbox (mark
reviewed/applied/rejected without leaving the page).
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from store import DB_PATH  # noqa: E402

STATUS_OPTIONS = ["new", "reviewed", "applied", "rejected", "likely_closed"]
TIER_CSS_CLASS = {"A": "tier-a", "B": "tier-b", "C": "tier-c"}  # combined values (e.g. "A/B") fall back to the neutral chip style

st.set_page_config(page_title="AI Policy Job Tracker", page_icon="🧭", layout="wide")

# Streamlit doesn't expose its active theme's colors as CSS variables to plain
# st.markdown HTML (only to the newer iframe-based Components v2 — verified
# empirically, not just from docs). So instead of guessing via a
# prefers-color-scheme media query — which would only track the OS setting,
# not the in-app Settings-menu toggle — read the REAL active theme via
# st.context.theme.type and inject matching literal colors for our custom
# card/chip HTML. Palette matches .streamlit/config.toml's [theme.light] /
# [theme.dark] (kept in sync by hand — small enough surface not to bother
# with a shared source of truth).
# Per-tier chip colors: A blue, B green, C red — distinct hue per tier instead
# of one shared accent color for all three (which read as "blue on blue" for
# every tier alike). Each is a translucent tint of a saturated mid-tone over
# text in the same hue family but pushed to the opposite lightness extreme
# (very dark ink in light theme, near-pastel in dark theme) — contrast-checked
# 5.3–7.5:1 across all six theme×tier combinations, red included (red's low
# luminance weight in the WCAG formula makes it the easiest to get wrong).
LIGHT = {
    "ink_soft": "#565c63", "rule": "#dcdcd4", "accent": "#1E88E5",
    "chip_bg": "#e2e6ea", "chip_fg": "#565c63",
    "tier_colors": {
        "A": ("rgba(30,136,229,0.14)", "#0d47a1"),
        "B": ("rgba(46,125,50,0.14)", "#1b5e20"),
        "C": ("rgba(211,47,47,0.14)", "#b71c1c"),
    },
}
DARK = {  # deep summer night — deep navy sky + firefly-lime, not generic dark-gray
    "ink_soft": "#a7bfe0", "rule": "#28407a", "accent": "#c0e86e",
    "chip_bg": "#1c3155", "chip_fg": "#c7d6ee",
    "tier_colors": {
        "A": ("rgba(100,181,246,0.18)", "#90caf9"),
        "B": ("rgba(129,199,132,0.18)", "#a5d6a7"),
        "C": ("rgba(229,115,115,0.18)", "#ef9a9a"),
    },
}
palette = DARK if st.context.theme.type == "dark" else LIGHT

# Streamlit fills multiselect tags and the checkbox tick with primaryColor and
# draws white text/strokes on top unconditionally (verified empirically via
# chrome-devtools — not auto-contrasted against the theme color's lightness).
# A light accent (dark theme's firefly-lime) + hardcoded white text is close to
# unreadable, so both themes' on-accent glyphs are forced to a fixed dark ink
# instead — chosen dark enough to stay legible against light-theme's medium
# blue accent too (contrast-checked ~5:1 there, ~13:1 against the lime).
ACCENT_INK = "#081422"

st.markdown(
    f"""
    <style>
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        border-radius: 6px !important;
    }}
    .card-title {{ font-size: 1.05rem; font-weight: 700; margin-bottom: 0.1rem; }}
    .card-org {{ font-size: 0.85rem; color: {palette['ink_soft']}; margin-bottom: 0.4rem; }}
    .card-chip {{
        display: inline-block; font-family: ui-monospace, monospace; font-size: 0.68rem;
        letter-spacing: 0.03em; text-transform: uppercase; padding: 0.1rem 0.45rem;
        border-radius: 2px; margin-right: 0.3rem; background: {palette['chip_bg']}; color: {palette['chip_fg']};
    }}
    .card-chip.tier-a {{ background: {palette['tier_colors']['A'][0]}; color: {palette['tier_colors']['A'][1]}; }}
    .card-chip.tier-b {{ background: {palette['tier_colors']['B'][0]}; color: {palette['tier_colors']['B'][1]}; }}
    .card-chip.tier-c {{ background: {palette['tier_colors']['C'][0]}; color: {palette['tier_colors']['C'][1]}; }}

    /* legible text/icons on primaryColor-filled widgets — see ACCENT_INK above */
    [data-baseweb="tag"] {{ color: {ACCENT_INK} !important; }}
    [data-baseweb="tag"] svg {{ fill: {ACCENT_INK} !important; }}
    [data-testid="stCheckbox"] svg polyline {{ stroke: {ACCENT_INK} !important; }}

    /* Print does nothing useful here and the theme toggle now lives in the
       fixed .st-key-theme-switch control below — hide both from the native
       "⋮" menu so the action isn't offered twice (Rerun/Clear cache/Deploy
       are already dropped app-wide via client.toolbarMode = "viewer").
       Record screen is dropped outright — not a feature this tool needs —
       specifically because the theme-switch script below has to briefly
       open this same native menu to click the real theme button, and
       hiding it with JS at the moment it opens wasn't reliably faster than
       the first paint (a real frame of "Record screen" was still visible in
       manual testing). Removing the item from the DOM entirely means there
       is nothing left to flash regardless of timing. */
    [data-testid="stMainMenuItem-print"],
    [data-testid="stMainMenuItem-recordScreencast"],
    [data-testid^="stMainMenuItem-theme-"] {{ display: none !important; }}

    /* Theme switcher, docked where Streamlit's Deploy button used to sit.
       Streamlit's own header (.stAppHeader) sits at z-index 999990 — anything
       meant to float above it needs to clear that, not an arbitrary "high"
       number (verified empirically; a naive z-index: 1000 rendered invisibly
       *underneath* the header). */
    .st-key-theme-switch {{
        position: fixed; top: 0.55rem; right: 4rem; z-index: 999995;
        width: 140px; height: 34px;
    }}
    .st-key-theme-switch iframe {{ width: 100%; height: 100%; border: none; }}

    /* Live card count, right-aligned above the grid. Uses the same neutral
       chip_bg/chip_fg pairing as the workplace/location chips (proven legible
       in both themes already) rather than the lime tier_bg/tier_fg tint,
       which read as low-contrast lime-on-lime in dark mode. */
    .vacancy-counter {{
        display: inline-block; font-size: 1.1rem; font-weight: 700;
        padding: 0.4rem 1.1rem; border-radius: 999px;
        background: {palette['chip_bg']}; color: {palette['chip_fg']};
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Theme buttons in Streamlit's native "⋮" menu are real, working controls tied
# to its internal (unexported) theme state — there is no public API to set the
# theme ourselves. So this dropdown doesn't reimplement switching; it opens
# the native menu off-screen-of-attention and clicks the matching real item
# for us (data-testid values reverse-engineered from the bundled frontend JS:
# stMainMenuButton, stMainMenuItem-theme-{System,Light,Dark}).
#
# This has to be st.iframe(html_string), not st.markdown(unsafe_allow_html=True):
# verified empirically that Streamlit strips inline event-handler attributes
# (onchange/onclick) even with unsafe_allow_html — that's also why last
# round's onclick="window.print()" button silently did nothing. st.iframe
# renders a real standalone document into an unsandboxed same-origin iframe
# (Streamlit's own docstring confirms "same-origin access to the Streamlit
# app"), so real <script>/addEventListener code executes, and
# window.parent.document reaches the real page to click the real button.
#
# A native <select> can't do two things this needs: (1) an <option> can only
# ever hold plain text — no nested <svg>, so a monochrome icon per row is
# impossible there, and the 🌓☀️🌙 emoji used originally are inherently
# full-color glyphs that ignore any `color` CSS entirely, hence "yellow
# crescent" regardless of theme; (2) the OPEN option list is OS-native popup
# chrome in most browsers and largely ignores page CSS, which is why its text
# came out illegible in dark mode. A hand-rolled trigger+listbox pair (plain
# divs/buttons) sidesteps both — full control over colors, and icons are just
# inline SVG with fill/stroke="currentColor" so they pick up the theme ink
# automatically instead of carrying their own fixed color.
_resolved_theme = st.context.theme.type or "light"  # None in bare/test mode; "system" can't be detected either way
_ink = "#f3ecd9" if _resolved_theme == "dark" else "#31333f"
_panel_bg = "#1a1f3f" if _resolved_theme == "dark" else "#ffffff"
_hover_bg = "rgba(255,255,255,0.10)" if _resolved_theme == "dark" else "rgba(0,0,0,0.06)"

# Feather-icons paths (MIT) — line-art, no fill color baked in, so `currentColor`
# is the only color source: dark ink in light theme, light ink in dark theme.
_ICON_SYSTEM = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>'
_ICON_LIGHT = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>'
_ICON_DARK = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'
_THEME_ICONS = {"System": _ICON_SYSTEM, "Light": _ICON_LIGHT, "Dark": _ICON_DARK}

_current_label = _resolved_theme.capitalize()  # best-effort: shows Light/Dark, can't show "System"
_options_html = "".join(
    f'<button type="button" class="ts-option" data-value="{label}">{icon}<span>{label}</span></button>'
    for label, icon in _THEME_ICONS.items()
)

_THEME_SWITCH_TEMPLATE = """
<html><body style="margin:0; background:transparent; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div class="ts-wrap">
    <button type="button" id="ts-trigger" class="ts-trigger">
        <span id="ts-current-icon">__CURRENT_ICON__</span>
        <span id="ts-current-label">__CURRENT_LABEL__</span>
        <span class="ts-caret">&#9662;</span>
    </button>
    <div id="ts-list" class="ts-list" hidden>__OPTIONS_HTML__</div>
</div>
<style>
* { box-sizing: border-box; }
.ts-wrap { position: relative; }
.ts-trigger {
    width: 100%; height: 34px; display: flex; align-items: center; gap: 6px;
    padding: 0 8px; border-radius: 0.4rem; border: 1px solid __RULE__;
    background: transparent; color: __INK__; cursor: pointer; font-size: 0.8rem;
}
.ts-trigger .ts-caret { margin-left: auto; opacity: 0.65; font-size: 0.65rem; }
.ts-list {
    position: absolute; top: 38px; right: 0; min-width: 118px;
    background: __PANEL_BG__; border: 1px solid __RULE__; border-radius: 0.4rem;
    box-shadow: 0 4px 14px rgba(0,0,0,0.35); overflow: hidden; z-index: 10;
}
.ts-option {
    width: 100%; display: flex; align-items: center; gap: 6px; padding: 0.4rem 0.6rem;
    background: transparent; border: none; color: __INK__; cursor: pointer;
    font-size: 0.8rem; text-align: left;
}
.ts-option:hover { background: __HOVER_BG__; }
</style>
<script>
var trigger = document.getElementById('ts-trigger');
var list = document.getElementById('ts-list');

// The enclosing st.iframe is only 34px tall (just the trigger). An <iframe>
// clips its own content at its own box — an absolutely-positioned dropdown
// "below" the trigger would be cut off, not overflow into the outer page —
// so the list opening/closing resizes the real <iframe> element itself via
// window.frameElement, which same-origin scripts can reach directly.
function setOpen(open) {
    list.hidden = !open;
    if (window.frameElement) { window.frameElement.style.height = open ? '150px' : '34px'; }
}
trigger.addEventListener('click', function (e) {
    e.stopPropagation();
    setOpen(list.hidden);
});
document.addEventListener('click', function () { setOpen(false); });

Array.prototype.forEach.call(document.querySelectorAll('.ts-option'), function (opt) {
    opt.addEventListener('click', function (e) {
        e.stopPropagation();
        var v = opt.getAttribute('data-value');
        setOpen(false);

        var doc = window.parent.document;
        var mm = doc.querySelector('[data-testid=stMainMenuButton]');
        if (!mm) { return; }
        // Click exactly ONCE. An earlier version re-clicked mm on every retry
        // until aria-expanded read "true" — but that check runs synchronously
        // right after click(), before React has necessarily flushed the
        // attribute update, so a still-closed reading didn't always mean the
        // click failed. Clicking again anyway just toggled an already-opening
        // menu back shut, which is what left the "⋮" menu (Record screen /
        // About) sitting visibly open after selecting a theme — the retry was
        // curing a false alarm by causing a real bug. Polling (read-only) for
        // the state to catch up is enough; clicking is a one-shot action.
        mm.click();
        var checks = 0;
        function waitForMenuOpen() {
            if (mm.getAttribute('aria-expanded') === 'true') {
                // The popover briefly showed real menu items (Record screen,
                // About) on screen before the reload cut it off — reload is
                // fast but not instant, so that flash was genuinely visible,
                // not just a test artifact. Hiding the popover the moment it's
                // confirmed open (clicks still work on a hidden element) means
                // the user only ever sees the trigger, never Streamlit's menu.
                var popover = doc.querySelector('[data-testid=stMainMenuPopover]');
                if (popover) { popover.style.visibility = 'hidden'; }
                var item = doc.querySelector('[data-testid=stMainMenuItem-theme-' + v + ']');
                if (item) {
                    item.click();
                    // Our own colors (company name, tier chips, this control's
                    // own label) are plain Python-computed CSS from
                    // st.context.theme.type at the LAST script run — the
                    // native click above only updates Streamlit's own
                    // reactive chrome, not that already-rendered output, so
                    // without a reload the page ends up showing the new
                    // theme's native widgets next to our OLD theme's colors
                    // (pale-on-pale, unreadable). Reloading re-runs app.py
                    // against the now-current theme, fixing both that and any
                    // leftover UI state in one deterministic step.
                    setTimeout(function () { window.parent.location.reload(); }, 120);
                }
                return;
            }
            if (checks++ > 10) { return; }  // ~300ms cap; give up quietly rather than click again
            setTimeout(waitForMenuOpen, 30);
        }
        setTimeout(waitForMenuOpen, 30);
    });
});
</script>
</body></html>
"""
_theme_switch_html = (
    _THEME_SWITCH_TEMPLATE
    .replace("__CURRENT_ICON__", _THEME_ICONS.get(_current_label, _ICON_SYSTEM))
    .replace("__CURRENT_LABEL__", _current_label)
    .replace("__OPTIONS_HTML__", _options_html)
    .replace("__RULE__", palette["rule"])
    .replace("__INK__", _ink)
    .replace("__PANEL_BG__", _panel_bg)
    .replace("__HOVER_BG__", _hover_bg)
)
with st.container(key="theme-switch"):
    st.iframe(_theme_switch_html, height=34)


@st.cache_data(ttl=5)
def load_postings() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM postings ORDER BY COALESCE(posted_at, first_seen) DESC", conn
    )
    conn.close()
    return df


def set_status(ats_id: str, source: str, new_status: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE postings SET status=? WHERE source=? AND ats_id=?",
        (new_status, source, ats_id),
    )
    conn.commit()
    conn.close()
    load_postings.clear()


# A simplified transformer-block schematic, standing in for the compass — line
# art via stroke="currentColor" so it's genuinely monochrome and theme-aware
# with zero extra Python color logic (inline SVG inherits the heading's own
# cascaded `color`, unlike an SVG loaded through a CSS background-image url()).
#
# The icon-to-text gap can't be the h1's own `gap` (flexbox) — verified live
# that Streamlit wraps a markdown-rendered <h1>'s content in its own inner
# <span> for the anchor-link machinery, so the SVG and the text are both
# nested one level inside a single flex *item*, not two separate flex items;
# the h1's gap property has nothing to act on there (measured 0px between the
# icon and "A" despite gap: 0.6rem being set). margin-right on the SVG itself
# is a real sibling-to-sibling space inside that inner span, so it actually
# renders. Set to 10px — a live measurement of this exact heading's own
# rendered word-spacing (Range.getBoundingClientRect between "Policy" and
# "Job") came out to ~8.8px, so 10px stays comfortably at or above it.
_LOGO_SVG = (
    '<svg viewBox="0 0 24 24" width="38" height="38" fill="none" stroke="currentColor" '
    'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" '
    'style="flex-shrink:0; margin-right:10px;">'
    '<rect x="7" y="16.5" width="10" height="4" rx="1"/>'
    '<rect x="7" y="10" width="10" height="4" rx="1"/>'
    '<rect x="7" y="3.5" width="10" height="4" rx="1"/>'
    '<path d="M5 18.5h2M17 18.5h2M5 12h2M17 12h2M5 5.5h2M17 5.5h2"/>'
    '<path d="M20 18.5c1.6 0 1.6-15 0-15" opacity="0.55"/>'
    "</svg>"
)
st.markdown(
    # The icon's own drawn strokes start ~8px inside its 38px box (the SVG
    # viewBox has empty margin around the schematic), so the glyph's visual
    # edge sits noticeably right of the "Refresh from DB" button below it.
    # -8px on the whole heading brings the drawn edge back in line with it.
    # (Not re-checked pixel-for-pixel in a browser this round — nudge further
    # if it's still off.)
    # display:flex/gap here doesn't reach the icon-text spacing (see the note
    # on _LOGO_SVG above) — kept only for the vertical centering of Streamlit's
    # inner content span against its (empty, but still flex-participating)
    # anchor-link span.
    f'<h1 style="display:flex; align-items:center; margin-left:-8px;">{_LOGO_SVG}AI Policy Job Tracker</h1>',
    unsafe_allow_html=True,
)

if st.button("🔄 Refresh from DB"):
    load_postings.clear()
    st.rerun()

df = load_postings()

if df.empty:
    st.info("No postings in data/jobs.db yet — run `python3 scripts/run.py` first.")
    st.stop()

with st.sidebar:
    st.header("Filters")

    tiers = sorted(df["tier"].dropna().unique())
    tier_filter = st.multiselect("Tier", tiers, default=tiers)

    orgs = sorted(df["org"].unique())
    org_filter = st.multiselect("Organization", orgs, default=orgs)

    hide_closed = st.checkbox("Hide likely_closed / rejected", value=True)

    remote_only = st.checkbox("Only remote", value=False)

    query = st.text_input("Search title/description")

view = df[df["tier"].isin(tier_filter) & df["org"].isin(org_filter)]
if hide_closed:
    view = view[~view["status"].isin(["likely_closed", "rejected"])]
if remote_only:
    view = view[view["workplace_type"].str.lower() == "remote"]
if query:
    q = query.lower()
    mask = view["title"].str.lower().str.contains(q, na=False) | view["description"].str.lower().str.contains(q, na=False)
    view = view[mask]

st.markdown(
    f"""
    <div style="display:flex; justify-content:flex-end; margin: 0 0 1rem 0;">
        <span class="vacancy-counter" role="status">Current vacancies: {len(view)}</span>
    </div>
    """,
    unsafe_allow_html=True,
)

COLS = 3
rows = [view.iloc[i : i + COLS] for i in range(0, len(view), COLS)]

for row in rows:
    cols = st.columns(COLS)
    for col, (_, posting) in zip(cols, row.iterrows()):
        with col:
            with st.container(border=True):
                st.markdown(f'<div class="card-title">{posting["title"]}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="card-org">{posting["org"]}</div>', unsafe_allow_html=True)

                chips = []
                if posting["tier"]:
                    tier_class = TIER_CSS_CLASS.get(str(posting["tier"]).strip().upper(), "")
                    chips.append(f'<span class="card-chip {tier_class}">Tier {posting["tier"]}</span>')
                if posting["workplace_type"]:
                    chips.append(f'<span class="card-chip">{posting["workplace_type"]}</span>')
                if posting["location"]:
                    chips.append(f'<span class="card-chip">{posting["location"]}</span>')
                st.markdown("".join(chips), unsafe_allow_html=True)

                st.write("")
                st.link_button("Open posting ↗", posting["url"], use_container_width=True)

                key = f"{posting['source']}:{posting['ats_id']}"
                current = posting["status"]
                new_status = st.selectbox(
                    "Status",
                    STATUS_OPTIONS,
                    index=STATUS_OPTIONS.index(current) if current in STATUS_OPTIONS else 0,
                    key=f"status_{key}",
                    label_visibility="collapsed",
                )
                if new_status != current:
                    set_status(posting["ats_id"], posting["source"], new_status)
                    st.rerun()

                with st.expander("Description"):
                    st.text(posting["description"] or "(no description)")
