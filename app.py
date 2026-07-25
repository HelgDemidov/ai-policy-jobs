"""Local card-view browser for tracked job postings.

Run with: .venv/bin/streamlit run app.py
Reads scripts/store.py's SQLite DB directly — read-only except for the
status field, which cards write back to via a selectbox (mark
reviewed/applied/rejected without leaving the page).
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from store import DB_PATH  # noqa: E402

STATUS_OPTIONS = ["new", "reviewed", "applied", "rejected", "likely_closed"]

st.set_page_config(page_title="Job Search Tracker", page_icon="🧭", layout="wide")

# Streamlit doesn't expose its active theme's colors as CSS variables to plain
# st.markdown HTML (only to the newer iframe-based Components v2 — verified
# empirically, not just from docs). So instead of guessing via a
# prefers-color-scheme media query — which would only track the OS setting,
# not the in-app Settings-menu toggle — read the REAL active theme via
# st.context.theme.type and inject matching literal colors for our custom
# card/chip HTML. Palette matches .streamlit/config.toml's [theme.light] /
# [theme.dark] (kept in sync by hand — small enough surface not to bother
# with a shared source of truth).
LIGHT = {
    "ink_soft": "#565c63", "rule": "#dcdcd4", "accent": "#1E88E5",
    "chip_bg": "#e2e6ea", "chip_fg": "#565c63",
    "tier_bg": "rgba(30,136,229,0.14)", "tier_fg": "#1565c0",
}
DARK = {  # deep summer night — warm indigo + firefly-gold, not generic dark-gray
    "ink_soft": "#c9bfe3", "rule": "#3a3163", "accent": "#f2b84b",
    "chip_bg": "#2c2555", "chip_fg": "#cabfe6",
    "tier_bg": "rgba(242,184,75,0.18)", "tier_fg": "#f2b84b",
}
palette = DARK if st.context.theme.type == "dark" else LIGHT

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
    .card-chip.tier {{ background: {palette['tier_bg']}; color: {palette['tier_fg']}; }}
    </style>
    """,
    unsafe_allow_html=True,
)


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


st.title("🧭 Job Search Tracker")

df = load_postings()

if df.empty:
    st.info("No postings in data/jobs.db yet — run `python3 scripts/run.py` first.")
    st.stop()

with st.sidebar:
    st.header("Filters")
    if st.button("🔄 Refresh from DB"):
        load_postings.clear()
        st.rerun()

    tiers = sorted(df["tier"].dropna().unique())
    tier_filter = st.multiselect("Tier", tiers, default=tiers)

    orgs = sorted(df["org"].unique())
    org_filter = st.multiselect("Organization", orgs, default=orgs)

    hide_closed = st.checkbox("Hide likely_closed / rejected", value=True)

    query = st.text_input("Search title/description")

view = df[df["tier"].isin(tier_filter) & df["org"].isin(org_filter)]
if hide_closed:
    view = view[~view["status"].isin(["likely_closed", "rejected"])]
if query:
    q = query.lower()
    mask = view["title"].str.lower().str.contains(q, na=False) | view["description"].str.lower().str.contains(q, na=False)
    view = view[mask]

st.caption(f"{len(view)} of {len(df)} tracked posting(s)")

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
                    chips.append(f'<span class="card-chip tier">Tier {posting["tier"]}</span>')
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
