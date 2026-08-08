"""
County Pipeline — Live Dashboard (rebuilt 2026-08-07)

Reads directly from output/dashboard/*.md — the actual real, verified
dossiers generated tonight — not from any intermediate CSV/sqlite that
could drift out of sync or carry stale/fabricated data. No hardcoded
county list; it picks up whatever counties actually have dossiers.

Card layout/styling borrowed from the older dashboard.py (dark cards,
labeled table rows, ranked expander list) — but every field shown here
is a real field that exists in the actual dossiers. Nothing invented
(no star ratings / confidence bars / timelines that don't exist in the
real pipeline output).

Two products, matching the real business model:
  - Pre-Auction Intel  (*_prop_intel_dossier.md) — Butte, Kern, Tehama, Fresno
  - Excess Proceeds    (*_excess_claim.md)        — Humboldt, Shasta, Tulare

Launch:
  streamlit run county_dashboard_live.py
"""
import re
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
DASHBOARD_DIR = ROOT / "output" / "dashboard"

st.set_page_config(page_title="County Pipeline — Live", layout="wide", page_icon="🗂️")

st.markdown("""
<style>
    html, body, [class*="css"] { font-family: -apple-system, 'Segoe UI', Inter, sans-serif; }
    h1, h2, h3 { font-weight: 800 !important; letter-spacing: -0.5px; }
    div[data-testid="metric-container"] {
        background: rgba(30, 30, 30, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 1rem 1.5rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .stDataFrame { border-radius: 12px; overflow: hidden; border: 1px solid rgba(255, 255, 255, 0.1); }
    [data-testid="stDeployButton"] { display: none !important; }
</style>
""", unsafe_allow_html=True)


def _grab(text, pattern, default=None):
    m = re.search(pattern, text)
    return m.group(1).strip() if m else default


def _money(s):
    if not s:
        return None
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_prop_intel(path: Path) -> dict:
    t = path.read_text(encoding="utf-8")
    county = path.name.split("_")[0].title()
    return {
        "kind": "Pre-Auction Intel",
        "county": county,
        # Prefer the new, explicit Assessor APN field; fall back to the old
        # "**APN**:" line for any not-yet-regenerated dossier (e.g. excess-
        # proceeds dossiers, which use a different template and still have
        # this line), then the H1 title's {{apn_dash}} as a last resort.
        "apn": (
            _grab(t, r"\*\*Assessor APN\*\*: `([^`]+)`")
            or _grab(t, r"\*\*APN\*\*: `([^`]+)`")
            or _grab(t, r"# Pre-Auction Property Intelligence Dossier: (\S+)")
        ),
        "tier": _grab(t, r"\*\*Opportunity Tier\*\*: \*\*([^*]+)\*\*"),
        "signal": _grab(t, r"(?:PRIORITY|PUBLIC-RECORD) SIGNAL: (.+?)\*\*"),
        "score": float(_grab(t, r"Seller Intent Score\*\* \| \*\*([\d.]+)", "0") or 0),
        "equity_pct": float(_grab(t, r"Estimated Equity Ratio\*\* \| \*\*([\d.]+)%", "0") or 0),
        # Prefer the new, honestly-labeled field; fall back to the old name
        # for any not-yet-regenerated dossier.
        "lien_risk": (
            _grab(t, r"Equity / Assessed-Value Indicator\*\* \| \*\*([^*]+)\*\*")
            or _grab(t, r"Lien Risk Tier\*\* \| \*\*([^*]+)\*\*")
        ),
        "min_bid": _money(_grab(t, r"Minimum Starting Bid\*\* \| \$([\d,.]+)")),
        "assessed": _money(_grab(t, r"Net Assessed Total Value\*\* \| \$([\d,.]+)")),
        "owner": _grab(t, r"Owner of Record\*\*: \*\*([^*]+)\*\*"),
        "entity_type": _grab(t, r"Owner Entity Type\*\*: ([^\n]+)"),
        "out_of_state": _grab(t, r"Out-of-State Owner\*\*: ([^\n]+)"),
        "situs": _grab(t, r"Property Situs Address\*\*: ([^\n]+)"),
        "tax_status": _grab(t, r"Tax Delinquency Status\*\*: ([^\n]+)"),
        "doc_number": _grab(t, r"Last Recorded Doc Number\*\*: `([^`]+)`"),
        "notice_status": _grab(t, r"Notice of Power to Sell / Default\*\*: ([^\n]+)"),
        "verification": _grab(t, r"Data Integrity Status\*\*: ([^\n]+)"),
        "data_gaps": _grab(t, r"Data Gap Audit\*\*: ([^\n]+)"),
        "source": _grab(t, r"Primary Source Endpoint\*\*: `([^`]+)`"),
        "auction_window": _grab(t, r"Predicted Auction Window\*\* \| ([^\n|]+)"),
        "file": str(path),
    }


def parse_excess(path: Path) -> dict:
    t = path.read_text(encoding="utf-8")
    county = path.name.split("_")[0].title()
    amount_raw = _grab(t, r"Excess Proceeds Available\*\* \| \*\*([^*]+)\*\*")
    return {
        "kind": "Excess Proceeds",
        "county": county,
        "apn": _grab(t, r"\*\*APN\*\*: `([^`]+)`"),
        "amount": _money(amount_raw),
        "amount_display": amount_raw,
        "owner": _grab(t, r"Owner of Record\*\* \| \*\*([^*]+)\*\*"),
        "deadline": _grab(t, r"Claim Deadline\*\* \| \*\*([^*]+)\*\*"),
        "urgency": _grab(t, r"Urgency Status\*\* \| ([^\n|]+)"),
        "recoverability": _grab(t, r"Recoverability Score\*\* \| \*\*([\d.]+)"),
        "locatability": _grab(t, r"Heir Locatability Tier\*\* \| ([^\n|]+)"),
        "situs": _grab(t, r"Situs Address\*\*: ([^\n]+)"),
        "verification": _grab(t, r"Verification Receipt\*\*: ([^\n]+)"),
        "file": str(path),
    }


@st.cache_data(ttl=30)
def load_data():
    prop_files = sorted(DASHBOARD_DIR.glob("*_prop_intel_dossier.md"))
    excess_files = sorted(DASHBOARD_DIR.glob("*_excess_claim.md"))
    prop_rows = [parse_prop_intel(p) for p in prop_files]
    excess_rows = [parse_excess(p) for p in excess_files]
    return pd.DataFrame(prop_rows), pd.DataFrame(excess_rows)


TIER_EMOJI = {
    "Level 1 (Prime Opportunity — Top 5%)": "🔴",
    "UNVERIFIED (Insufficient Source Data)": "⚪",
}


def tier_emoji(tier):
    if not tier:
        return "⚪"
    if "Level 1" in tier:
        return "🔴"
    if "Level 2" in tier:
        return "🟠"
    if "Level 3" in tier:
        return "🟡"
    if "UNVERIFIED" in tier:
        return "⚪"
    return "🟢"


def render_prop_card(row):
    verified = "UNVERIFIED" not in (row["verification"] or "")
    verif_badge = "✅ Verified" if verified else "⚪ Unverified"
    owner_display = row["owner"] or "UNKNOWN"
    money = lambda v: f"${v:,.2f}" if v is not None else "Unavailable"

    card = f"""
<div style='background:#111418; border:1px solid #2a2f36; border-radius:10px; padding:1.1rem 1.3rem; margin-bottom:0.5rem;'>
<table style='width:100%; border-collapse:collapse;'>
<tr><td style='color:#888; width:150px; vertical-align:top; padding:2px 8px 2px 0; font-size:0.9rem;'>County</td><td style='padding:2px 0;'>{row['county']} County</td></tr>
<tr><td style='color:#888; width:150px; vertical-align:top; padding:2px 8px 2px 0; font-size:0.9rem;'>APN</td><td style='padding:2px 0; font-family:monospace;'>{row['apn']}</td></tr>
<tr><td style='color:#888; width:150px; vertical-align:top; padding:2px 8px 2px 0; font-size:0.9rem;'>Situs</td><td style='padding:2px 0;'>{row['situs'] or '—'}</td></tr>
<tr><td style='color:#888; width:150px; vertical-align:top; padding:2px 8px 2px 0; font-size:0.9rem;'>Owner</td><td style='padding:2px 0;'>{owner_display} <span style='color:#666; font-size:0.85rem;'>({row['entity_type'] or 'Unknown'}{', out-of-state' if row['out_of_state']=='Yes' else ''})</span></td></tr>
</table>
<hr style='border-color:#2a2f36; margin:0.7rem 0;'>

<h4 style='color:#e0e0e0; margin:0 0 0.4rem 0; font-size:0.95rem; font-weight:600;'>🔔 Signal</h4>
<div style='color:#f0b429; font-weight:600;'>{row['signal'] or '—'}</div>
<hr style='border-color:#2a2f36; margin:0.7rem 0;'>

<h4 style='color:#e0e0e0; margin:0 0 0.4rem 0; font-size:0.95rem; font-weight:600;'>Financials</h4>
<table style='width:100%; border-collapse:collapse;'>
<tr><td style='color:#888; width:150px; padding:2px 8px 2px 0; font-size:0.9rem;'>Assessed Value</td><td style='padding:2px 0; font-weight:600;'>{money(row['assessed'])}</td></tr>
<tr><td style='color:#888; width:150px; padding:2px 8px 2px 0; font-size:0.9rem;'>Minimum Bid</td><td style='padding:2px 0;'>{money(row['min_bid'])}</td></tr>
<tr><td style='color:#888; width:150px; padding:2px 8px 2px 0; font-size:0.9rem;'>Equity Ratio</td><td style='padding:2px 0;'>{row['equity_pct']:.1f}%</td></tr>
<tr><td style='color:#888; width:150px; padding:2px 8px 2px 0; font-size:0.9rem;' title='Derived from valuation/recorded-amount data only - not a title search, lien-priority analysis, encumbrance review, or legal conclusion'>Equity Signal</td><td style='padding:2px 0;'>{row['lien_risk'] or '—'}</td></tr>
</table>
<hr style='border-color:#2a2f36; margin:0.7rem 0;'>

<h4 style='color:#e0e0e0; margin:0 0 0.4rem 0; font-size:0.95rem; font-weight:600;'>Tax & Recorder Status</h4>
<table style='width:100%; border-collapse:collapse;'>
<tr><td style='color:#888; width:150px; padding:2px 8px 2px 0; font-size:0.9rem;'>Delinquency Status</td><td style='padding:2px 0;'>{row['tax_status'] or '—'}</td></tr>
<tr><td style='color:#888; width:150px; padding:2px 8px 2px 0; font-size:0.9rem;'>Last Recorded Doc</td><td style='padding:2px 0; font-family:monospace;'>{row['doc_number'] or '—'}</td></tr>
<tr><td style='color:#888; width:150px; padding:2px 8px 2px 0; font-size:0.9rem;'>Notice Status</td><td style='padding:2px 0;'>{row['notice_status'] or '—'}</td></tr>
</table>
<hr style='border-color:#2a2f36; margin:0.7rem 0;'>

<div style='background:{"#1e2940" if verified else "#2a1f1f"}; border:1px solid {"#3b4a6b" if verified else "#5a3a3a"}; border-radius:8px; padding:0.9rem 1rem;'>
<div style='font-weight:600; margin-bottom:0.4rem; color:{"#93c5fd" if verified else "#f0a0a0"};'>{verif_badge}</div>
<div style='color:#9ca3af; font-size:0.85rem;'>{row['verification'] or '—'}</div>
<div style='color:#6b7280; font-size:0.8rem; margin-top:0.4rem;'>Data gaps: {row['data_gaps'] or 'None found'}</div>
<div style='color:#6b7280; font-size:0.8rem; margin-top:0.2rem; font-family:monospace;'>Source: {row['source'] or '—'}</div>
</div>
</div>
"""
    st.markdown(card, unsafe_allow_html=True)


def render_excess_card(row):
    verified = "UNVERIFIED" in (row["verification"] or "") if row["verification"] else False
    card = f"""
<div style='background:#111418; border:1px solid #2a2f36; border-radius:10px; padding:1.1rem 1.3rem; margin-bottom:0.5rem;'>
<table style='width:100%; border-collapse:collapse;'>
<tr><td style='color:#888; width:150px; vertical-align:top; padding:2px 8px 2px 0; font-size:0.9rem;'>County</td><td style='padding:2px 0;'>{row['county']} County</td></tr>
<tr><td style='color:#888; width:150px; vertical-align:top; padding:2px 8px 2px 0; font-size:0.9rem;'>APN</td><td style='padding:2px 0; font-family:monospace;'>{row['apn']}</td></tr>
<tr><td style='color:#888; width:150px; vertical-align:top; padding:2px 8px 2px 0; font-size:0.9rem;'>Situs</td><td style='padding:2px 0;'>{row['situs'] or '—'}</td></tr>
<tr><td style='color:#888; width:150px; vertical-align:top; padding:2px 8px 2px 0; font-size:0.9rem;'>Claimant of Record</td><td style='padding:2px 0;'>{row['owner'] or 'UNKNOWN'}</td></tr>
</table>
<hr style='border-color:#2a2f36; margin:0.7rem 0;'>

<h4 style='color:#e0e0e0; margin:0 0 0.4rem 0; font-size:0.95rem; font-weight:600;'>💰 Claim</h4>
<div style='font-size:1.3rem; font-weight:700; color:#4ade80;'>{row['amount_display'] or '—'}</div>
<table style='width:100%; border-collapse:collapse; margin-top:0.5rem;'>
<tr><td style='color:#888; width:150px; padding:2px 8px 2px 0; font-size:0.9rem;'>Claim Deadline</td><td style='padding:2px 0; font-weight:600;'>{row['deadline'] or '—'}</td></tr>
<tr><td style='color:#888; width:150px; padding:2px 8px 2px 0; font-size:0.9rem;'>Urgency</td><td style='padding:2px 0;'>{row['urgency'] or '—'}</td></tr>
<tr><td style='color:#888; width:150px; padding:2px 8px 2px 0; font-size:0.9rem;'>Recoverability Score</td><td style='padding:2px 0;'>{row['recoverability'] or '—'} / 100</td></tr>
<tr><td style='color:#888; width:150px; padding:2px 8px 2px 0; font-size:0.9rem;'>Heir Locatability</td><td style='padding:2px 0;'>{row['locatability'] or '—'}</td></tr>
</table>
<hr style='border-color:#2a2f36; margin:0.7rem 0;'>

<div style='background:#1e2940; border:1px solid #3b4a6b; border-radius:8px; padding:0.9rem 1rem;'>
<div style='color:#9ca3af; font-size:0.85rem;'>{row['verification'] or '—'}</div>
</div>
</div>
"""
    st.markdown(card, unsafe_allow_html=True)


df_prop, df_excess = load_data()

st.title("🗂️ County Pipeline — Live Dashboard")
st.caption(f"Reading directly from `{DASHBOARD_DIR.relative_to(ROOT)}` — real dossiers only, no cached CSVs.")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Pre-Auction dossiers", len(df_prop))
col2.metric("Counties (pre-auction)", df_prop["county"].nunique() if len(df_prop) else 0)
col3.metric("Excess-proceeds leads", len(df_excess))
real_excess_total = df_excess["amount"].dropna().sum() if len(df_excess) else 0
col4.metric("Confirmed excess proceeds", f"${real_excess_total:,.0f}")

if st.button("🔄 Refresh from disk"):
    st.cache_data.clear()
    st.rerun()

tab1, tab2 = st.tabs(["📋 Pre-Auction Intel", "💰 Excess Proceeds"])

with tab1:
    if df_prop.empty:
        st.info("No pre-auction dossiers found yet.")
    else:
        st.subheader("Filters")
        c1, c2, c3 = st.columns([2, 2, 3])
        counties = sorted(df_prop["county"].unique())
        sel_counties = c1.multiselect("County", counties, default=counties, key="pi_counties")
        tiers = sorted(df_prop["tier"].dropna().unique())
        sel_tiers = c2.multiselect("Opportunity tier", tiers, default=tiers, key="pi_tiers")
        search = c3.text_input("Search (owner, APN, situs)", key="pi_search")

        view = df_prop[df_prop["county"].isin(sel_counties) & df_prop["tier"].isin(sel_tiers)]
        if search:
            s = search.lower()
            mask = (
                view["owner"].fillna("").str.lower().str.contains(s)
                | view["apn"].fillna("").str.lower().str.contains(s)
                | view["situs"].fillna("").str.lower().str.contains(s)
            )
            view = view[mask]

        sort_col = st.selectbox(
            "Sort by", ["score", "assessed", "min_bid", "equity_pct"],
            format_func=lambda x: {"score": "Seller Intent Score", "assessed": "Assessed Value",
                                    "min_bid": "Minimum Bid", "equity_pct": "Equity %"}[x],
            key="pi_sort",
        )
        view = view.sort_values(sort_col, ascending=False).reset_index(drop=True)

        st.write(f"**{len(view)}** of {len(df_prop)} dossiers match")

        st.download_button(
            "⬇️ Download filtered as CSV",
            view.drop(columns=["file"]).to_csv(index=False),
            file_name="pre_auction_intel_filtered.csv",
            mime="text/csv",
        )

        st.markdown("---")
        st.subheader("Ranked Opportunity Pipeline")

        MAX_CARDS = 100
        if len(view) > MAX_CARDS:
            st.caption(f"Showing top {MAX_CARDS} of {len(view)} by current sort — narrow with filters to see more.")
        for idx, row in view.head(MAX_CARDS).iterrows():
            emoji = tier_emoji(row["tier"])
            owner_short = row["owner"] or "UNKNOWN"
            bid = f"${row['min_bid']:,.0f}" if row["min_bid"] is not None else "N/A"
            title = f"{emoji} #{idx+1} · Score {row['score']:.0f} · {owner_short} · Min Bid {bid} · {row['county']}"
            with st.expander(title, expanded=(idx == 0)):
                render_prop_card(row)

with tab2:
    if df_excess.empty:
        st.info("No excess-proceeds leads found yet.")
    else:
        st.subheader("Filters")
        c1, c2 = st.columns([2, 3])
        counties_e = sorted(df_excess["county"].unique())
        sel_counties_e = c1.multiselect("County", counties_e, default=counties_e, key="ep_counties")
        search_e = c2.text_input("Search (owner, APN, situs)", key="ep_search")

        view_e = df_excess[df_excess["county"].isin(sel_counties_e)]
        if search_e:
            s = search_e.lower()
            mask = (
                view_e["owner"].fillna("").str.lower().str.contains(s)
                | view_e["apn"].fillna("").str.lower().str.contains(s)
                | view_e["situs"].fillna("").str.lower().str.contains(s)
            )
            view_e = view_e[mask]

        view_e = view_e.sort_values("amount", ascending=False, na_position="last").reset_index(drop=True)

        st.write(f"**{len(view_e)}** of {len(df_excess)} leads match — "
                 f"**${view_e['amount'].dropna().sum():,.2f}** in confirmed excess proceeds shown")

        st.download_button(
            "⬇️ Download filtered as CSV",
            view_e.drop(columns=["file"]).to_csv(index=False),
            file_name="excess_proceeds_filtered.csv",
            mime="text/csv",
        )

        st.markdown("---")
        st.subheader("Ranked Claim Pipeline")

        for idx, row in view_e.iterrows():
            amt = row["amount_display"] or "—"
            owner_short = row["owner"] or "UNKNOWN"
            title = f"💰 #{idx+1} · {amt} · {owner_short} · {row['county']} · Deadline {row['deadline'] or '—'}"
            with st.expander(title, expanded=(idx == 0)):
                render_excess_card(row)
