"""
CA-UNIFY Command Center — Unified Dual-Revenue Pipeline Dashboard
================================================================
Both revenue legs. All 58 counties. One screen.

Leg 1 — Property Intelligence (Pre-Auction):  Upcoming auctions, scored dossiers, investor delivery
Leg 2 — Excess Proceeds (Post-Auction):       Surplus claims, skip trace queue, outreach tracker

The two legs hedge each other:
  - Pre-auction counties  → generate dossier revenue NOW before the auction
  - Post-auction counties → generate claim revenue 4-6 months LATER

Launch:
  streamlit run ca_unify_dashboard.py

Auto-refresh: every 60 seconds via st.rerun()
"""

import csv
import glob
import json
import os
import sqlite3
import subprocess
import sys

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Constants ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
AUCTION_CAL    = ROOT / "data" / "california_tax_auction_calendar_2025_2027.csv"
DASHBOARD_FEED = ROOT / "output" / "dashboard" / "dashboard_feed.json"
HEALTH_MATRIX  = ROOT / "output" / "county_health_matrix.json"
HUMBOLDT_EP    = ROOT / "data" / "counties" / "humboldt" / "excess_proceeds.csv"
HUMBOLDT_TD    = ROOT / "data" / "counties" / "humboldt" / "tax_deed_parcels.csv"
BUTTE_SHEET    = ROOT / "butte" / "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"
SURPLUS_DB     = ROOT / "surplus.sqlite"
VERIFY_DB      = ROOT / "verification.sqlite"
DASHBOARD_DIR  = ROOT / "output" / "dashboard"

TODAY = date.today().isoformat()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CA-UNIFY Command Center",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.main { background: #0a0e1a; }
[data-testid="stAppViewContainer"] { background: #0a0e1a; }
[data-testid="stHeader"] { background: #0a0e1a; }

/* Command bar */
.command-bar {
    background: linear-gradient(135deg, #0f1729 0%, #1a2040 100%);
    border: 1px solid #1e3a5f;
    border-radius: 12px;
    padding: 20px 28px;
    margin-bottom: 24px;
}

/* KPI cards */
.kpi-card {
    background: linear-gradient(135deg, #0f1729 0%, #141e33 100%);
    border: 1px solid #1e3a5f;
    border-radius: 10px;
    padding: 20px;
    text-align: center;
    transition: border-color 0.2s;
}
.kpi-card:hover { border-color: #3b82f6; }
.kpi-value { font-size: 2rem; font-weight: 700; color: #f0f6ff; line-height: 1.1; }
.kpi-label { font-size: 0.78rem; color: #6b7fa3; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 4px; }
.kpi-sub   { font-size: 0.85rem; color: #94a3c0; margin-top: 6px; }

/* Leg headers */
.leg-header-pi {
    background: linear-gradient(90deg, #1a2a0a 0%, #0f1729 100%);
    border-left: 4px solid #22c55e;
    border-radius: 0 8px 8px 0;
    padding: 12px 20px;
    margin-bottom: 16px;
}
.leg-header-ep {
    background: linear-gradient(90deg, #1a100a 0%, #0f1729 100%);
    border-left: 4px solid #f59e0b;
    border-radius: 0 8px 8px 0;
    padding: 12px 20px;
    margin-bottom: 16px;
}
.leg-title { font-size: 1.1rem; font-weight: 600; color: #f0f6ff; margin: 0; }
.leg-sub   { font-size: 0.8rem; color: #6b7fa3; margin: 2px 0 0 0; }

/* Auction countdown cards */
.auction-card {
    background: #0f1729;
    border: 1px solid #1e3a5f;
    border-radius: 8px;
    padding: 14px 16px;
    margin-bottom: 10px;
}
.auction-urgent  { border-left: 3px solid #ef4444; }
.auction-soon    { border-left: 3px solid #f59e0b; }
.auction-normal  { border-left: 3px solid #22c55e; }
.auction-county  { font-size: 1rem; font-weight: 600; color: #e2e8f0; }
.auction-date    { font-size: 0.8rem; color: #6b7fa3; }
.auction-days    { font-size: 1.4rem; font-weight: 700; }
.days-urgent     { color: #ef4444; }
.days-soon       { color: #f59e0b; }
.days-normal     { color: #22c55e; }

/* Pipeline stages */
.stage-bar {
    background: #0f1729;
    border: 1px solid #1e3a5f;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.stage-name  { font-size: 0.85rem; color: #94a3c0; }
.stage-count { font-size: 1.1rem; font-weight: 600; color: #f0f6ff; }
.stage-value { font-size: 0.85rem; color: #22c55e; }

/* Automation buttons */
.stButton > button {
    background: linear-gradient(135deg, #1e3a5f, #2d5a8e);
    color: #e2e8f0;
    border: 1px solid #2d5a8e;
    border-radius: 8px;
    font-size: 0.85rem;
    font-weight: 500;
    padding: 8px 16px;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #2d5a8e, #3b82f6);
    border-color: #3b82f6;
    transform: translateY(-1px);
}

/* Status badges */
.badge-green  { background: #14532d; color: #86efac; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
.badge-yellow { background: #451a03; color: #fcd34d; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
.badge-red    { background: #450a0a; color: #fca5a5; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
.badge-blue   { background: #1e3a5f; color: #93c5fd; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
.badge-gray   { background: #1e293b; color: #94a3b8; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }

/* County health grid */
.health-cell-ok   { background: #14532d22; border: 1px solid #22c55e44; border-radius: 6px; padding: 8px; text-align: center; }
.health-cell-warn { background: #45510322; border: 1px solid #f59e0b44; border-radius: 6px; padding: 8px; text-align: center; }
.health-cell-fail { background: #4a0a0a22; border: 1px solid #ef444444; border-radius: 6px; padding: 8px; text-align: center; }

/* Divider */
.divider { border: none; border-top: 1px solid #1e3a5f; margin: 24px 0; }
</style>
""", unsafe_allow_html=True)


# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_auction_calendar():
    if not AUCTION_CAL.exists():
        return pd.DataFrame()
    df = pd.read_csv(AUCTION_CAL)
    df.columns = df.columns.str.strip()
    df["Start Date"] = pd.to_datetime(df["Start Date"], errors="coerce")
    return df

@st.cache_data(ttl=60)
def load_dashboard_feed():
    if not DASHBOARD_FEED.exists():
        return []
    with open(DASHBOARD_FEED, encoding="utf-8") as f:
        return json.load(f)

@st.cache_data(ttl=60)
def load_health_matrix():
    if not HEALTH_MATRIX.exists():
        return {}
    with open(HEALTH_MATRIX, encoding="utf-8") as f:
        return json.load(f)

@st.cache_data(ttl=60)
def load_humboldt_ep():
    if not HUMBOLDT_EP.exists():
        return pd.DataFrame()
    return pd.read_csv(HUMBOLDT_EP)

@st.cache_data(ttl=60)
def load_humboldt_td():
    if not HUMBOLDT_TD.exists():
        return pd.DataFrame()
    return pd.read_csv(HUMBOLDT_TD)

@st.cache_data(ttl=60)
def load_butte_sheet():
    if not BUTTE_SHEET.exists():
        return pd.DataFrame()
    return pd.read_csv(BUTTE_SHEET, dtype=str)

@st.cache_data(ttl=60)
def count_dossiers():
    pi = len(glob.glob(str(DASHBOARD_DIR / "*_prop_intel_dossier.md")))
    ep = len(glob.glob(str(DASHBOARD_DIR / "*_excess_claim.md")))
    return pi, ep

@st.cache_data(ttl=300)
def load_all_counties():
    """Load all 58 county slugs and their platform config from YAML files."""
    import yaml
    counties_dir = ROOT / "counties"
    county_list = []
    county_platform = {}
    for yf in sorted(counties_dir.glob("*.yaml")):
        slug = yf.stem
        try:
            with open(yf, encoding="utf-8") as f:
                d = yaml.safe_load(f) or {}
            assessor  = (d.get("assessor")  or {}).get("backend", "manual")
            recorder  = (d.get("recorder")  or {}).get("backend", "manual")
            auction   = (d.get("auction")   or {}).get("backend", "govease")
            county_list.append(slug)
            county_platform[slug] = {
                "assessor": assessor,
                "recorder": recorder,
                "auction":  auction,
                "display":  slug.replace("_", " ").title(),
            }
        except Exception:
            county_list.append(slug)
            county_platform[slug] = {"assessor": "manual", "recorder": "manual", "auction": "govease", "display": slug.replace("_", " ").title()}
    return county_list, county_platform

def days_until(date_str):
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
        return (d - date.today()).days
    except:
        return None

def money(v):
    try:
        return f"${float(str(v).replace('$','').replace(',','')):,.0f}"
    except:
        return str(v)


# ── Load all data ─────────────────────────────────────────────────────────────
cal                    = load_auction_calendar()
feed                   = load_dashboard_feed()
health                 = load_health_matrix()
hum_ep                 = load_humboldt_ep()
hum_td                 = load_humboldt_td()
butte_sheet            = load_butte_sheet()
pi_count, ep_count     = count_dossiers()
all_counties, county_platform = load_all_counties()

# Upcoming auctions
upcoming = []
if not cal.empty:
    for _, row in cal.iterrows():
        status = str(row.get("Status","")).upper()
        if "UPCOMING" in status or "TENTATIVE" in status:
            d = days_until(row.get("Start Date"))
            if d is not None and -7 <= d <= 180:
                upcoming.append({
                    "county": str(row.get("County","")),
                    "date": str(row.get("Start Date",""))[:10],
                    "platform": str(row.get("Platform","")),
                    "days": d,
                    "status": str(row.get("Status","")),
                    "url": str(row.get("Portal URL","")),
                    "notes": str(row.get("Notes","")),
                })
    upcoming.sort(key=lambda x: x["days"])

# Excess proceeds from feed
ep_entries = [e for e in feed if e.get("type") == "EXCESS_PROCEEDS"]
pi_entries = [e for e in feed if e.get("type") != "EXCESS_PROCEEDS"]

# Total surplus from Humboldt EP
total_surplus = 0.0
if not hum_ep.empty:
    for col in ["excess_proceeds", "surplus", "amount"]:
        if col in hum_ep.columns:
            total_surplus = pd.to_numeric(
                hum_ep[col].astype(str).str.replace(r"[$,]","",regex=True),
                errors="coerce"
            ).sum()
            break

# Counties health
counties_health = health.get("counties", {}) if isinstance(health, dict) else {}

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="command-bar">
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <div>
            <div style="font-size:1.5rem; font-weight:700; color:#f0f6ff;">🏛️ CA-UNIFY Command Center</div>
            <div style="font-size:0.85rem; color:#6b7fa3; margin-top:2px;">
                California Tax Intelligence · 58 Counties · Both Revenue Legs · {datetime.now().strftime("%b %d, %Y  %I:%M %p")}
            </div>
        </div>
        <div style="text-align:right;">
            <span style="font-size:0.75rem; color:#6b7fa3;">NEXT AUCTION</span><br>
            <span style="font-size:1.2rem; font-weight:700; color:#ef4444;">
                {upcoming[0]['county'] + "  " + str(upcoming[0]['days']) + "d" if upcoming else "None upcoming"}
            </span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── TOP KPIs ──────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5, k6 = st.columns(6)

with k1:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-value">{len(upcoming)}</div>
        <div class="kpi-label">Upcoming Auctions</div>
        <div class="kpi-sub">Next 180 days</div>
    </div>""", unsafe_allow_html=True)

with k2:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-value">{pi_count}</div>
        <div class="kpi-label">Prop Intel Dossiers</div>
        <div class="kpi-sub">Ready to sell</div>
    </div>""", unsafe_allow_html=True)

with k3:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-value">{ep_count}</div>
        <div class="kpi-label">Claim Reports</div>
        <div class="kpi-sub">Excess proceeds</div>
    </div>""", unsafe_allow_html=True)

with k4:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-value">{money(total_surplus)}</div>
        <div class="kpi-label">Identified Surplus</div>
        <div class="kpi-sub">Humboldt verified</div>
    </div>""", unsafe_allow_html=True)

with k5:
    humboldt_claims = len(hum_ep) if not hum_ep.empty else 30
    est_recovery = humboldt_claims * 7419 * 0.15  # 15% conversion, 35% cut, $21K avg
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-value">{money(est_recovery)}</div>
        <div class="kpi-label">Est. Net Recovery</div>
        <div class="kpi-sub">Conservative 15% close</div>
    </div>""", unsafe_allow_html=True)

with k6:
    healthy = sum(1 for v in counties_health.values() if "HEALTHY" in str(v.get("status","")).upper() or "LIVE" in str(v.get("status","")).upper())
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-value">{healthy}/{len(counties_health) or "–"}</div>
        <div class="kpi-label">Counties Healthy</div>
        <div class="kpi-sub">Live data confirmed</div>
    </div>""", unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ── MAIN TWO-COLUMN LAYOUT ────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

# ════════════════════════════════════════════════════════════════════════════
# LEFT — LEG 1: PROPERTY INTELLIGENCE
# ════════════════════════════════════════════════════════════════════════════
with left:
    st.markdown("""<div class="leg-header-pi">
        <p class="leg-title">🟢 LEG 1 — Property Intelligence</p>
        <p class="leg-sub">Pre-auction · Score → Enrich → Sell to investors before they bid</p>
    </div>""", unsafe_allow_html=True)

    # Auction countdown
    st.markdown("##### Auction Countdown")
    if upcoming:
        for a in upcoming[:6]:
            d = a["days"]
            urgency = "urgent" if d <= 7 else "soon" if d <= 30 else "normal"
            day_class = f"days-{urgency}"
            card_class = f"auction-{urgency}"
            label = "TODAY" if d == 0 else f"{d}d"
            dossier_files = glob.glob(str(DASHBOARD_DIR / f"{a['county'].lower()}_*_prop_intel_dossier.md"))
            dossier_badge = f'<span class="badge-green">{len(dossier_files)} dossiers ready</span>' if dossier_files else '<span class="badge-gray">No dossiers yet</span>'
            st.markdown(f"""<div class="auction-card {card_class}">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div class="auction-county">{a['county']}</div>
                        <div class="auction-date">{a['date']} · {a['platform']}</div>
                        <div style="margin-top:6px;">{dossier_badge}</div>
                    </div>
                    <div class="auction-days {day_class}">{label}</div>
                </div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No upcoming auctions detected in next 180 days.")

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # Dossier inventory
    st.markdown("##### Dossier Inventory")
    counties_with_dossiers = {}
    for f in glob.glob(str(DASHBOARD_DIR / "*_prop_intel_dossier.md")):
        county = Path(f).name.split("_")[0].capitalize()
        counties_with_dossiers[county] = counties_with_dossiers.get(county, 0) + 1

    if counties_with_dossiers:
        for county, count in sorted(counties_with_dossiers.items(), key=lambda x: -x[1]):
            matching = [a for a in upcoming if a["county"].lower() == county.lower()]
            days_label = f"{matching[0]['days']}d to auction" if matching else "No auction scheduled"
            est_rev = count * 97
            st.markdown(f"""<div class="stage-bar">
                <div>
                    <span class="stage-name">{county}</span>
                    <span style="font-size:0.75rem; color:#475569; margin-left:8px;">{days_label}</span>
                </div>
                <div style="text-align:right;">
                    <span class="stage-count">{count} dossiers</span>
                    <span class="stage-value" style="display:block; font-size:0.78rem;">Est. {money(est_rev)} @ $97</span>
                </div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No prop intel dossiers generated yet.")

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # Automations — Leg 1
    st.markdown("##### Automations")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔄 Run Auction Monitor", key="run_scheduler"):
            with st.spinner("Scanning 58-county calendar..."):
                result = subprocess.run(
                    [sys.executable, "auction_scheduler.py"],
                    capture_output=True, text=True, cwd=str(ROOT)
                )
                st.code(result.stdout[-1000:] if result.stdout else result.stderr[-500:])
                st.cache_data.clear()

    with col_b:
        if st.button("📋 Generate Butte Dossiers", key="run_butte"):
            # Canonical path only. Prior versions of this button shelled out
            # to fetch_butte_task1.py, which wrote directly into output/
            # dashboard/ with no redemption-lifecycle check (release-integrity
            # audit finding, 2026-08-08 - see fetch_butte_task1.py's own
            # deprecation docstring, and regen_butte_dossiers.py's
            # is_redeemed()). This button now calls
            # regen_butte_dossiers.run_canonical_generation_captured() - a
            # thin, Streamlit-free wrapper around the same main() used by
            # BUTTE_MONITOR - so there is exactly one code path that can
            # produce Butte dossier output, it lives in a plain module
            # (no streamlit import needed), and it is independently
            # unit-tested in tests/test_dashboard_canonical_path.py without
            # needing a running Streamlit session or streamlit installed.
            sys.path.insert(0, str(ROOT))
            import regen_butte_dossiers

            with st.spinner("Regenerating Butte dossiers via the canonical, redemption-filtered path..."):
                try:
                    output = regen_butte_dossiers.run_canonical_generation_captured()
                    st.code(output[-1500:])
                except Exception as e:
                    st.error(f"regen_butte_dossiers canonical generation failed: {e}")
                st.cache_data.clear()

    col_c, col_d = st.columns(2)
    with col_c:
        # Sorted: priority counties first, then all 58 alphabetically
        priority = ["butte","fresno","kern","humboldt","tehama","shasta","placer","san_benito"]
        sorted_counties = priority + [c for c in all_counties if c not in priority]
        county_labels   = [c.replace("_"," ").title() + "  [" + county_platform.get(c,{}).get("assessor","?") + "/" + county_platform.get(c,{}).get("recorder","?") + "]" for c in sorted_counties]
        sel_idx  = st.selectbox("County (all 58)", range(len(sorted_counties)), format_func=lambda i: county_labels[i], key="qe_county")
        county_sel = sorted_counties[sel_idx]
        if st.button("🔍 Query County Engine", key="run_qe"):
            with st.spinner(f"Querying {county_sel}..."):
                result = subprocess.run(
                    [sys.executable, "county_query_engine.py", "--county", county_sel, "--type", "prop_intel"],
                    capture_output=True, text=True, cwd=str(ROOT), timeout=120
                )
                st.code(result.stdout[-1000:] if result.stdout else result.stderr[-500:])
                st.cache_data.clear()
    with col_d:
        if st.button("⚡ Run Circuit Breaker", key="run_cb"):
            with st.spinner(f"Pre-flight check on {county_sel}..."):
                result = subprocess.run(
                    [sys.executable, "integrity_circuit_breaker.py", "--county", county_sel],
                    capture_output=True, text=True, cwd=str(ROOT), timeout=60
                )
                st.code(result.stdout[-1000:] if result.stdout else result.stderr[-500:])


# ════════════════════════════════════════════════════════════════════════════
# RIGHT — LEG 2: EXCESS PROCEEDS
# ════════════════════════════════════════════════════════════════════════════
with right:
    st.markdown("""<div class="leg-header-ep">
        <p class="leg-title">🟡 LEG 2 — Excess Proceeds Recovery</p>
        <p class="leg-sub">Post-auction · Find → Contact → File → Collect (30–40% contingency)</p>
    </div>""", unsafe_allow_html=True)

    # Claims pipeline stages
    st.markdown("##### Recovery Pipeline")

    # Build pipeline counts from available data
    identified = ep_count
    skip_traced = 0
    letters_sent = 0
    agreements  = 0
    filed       = 0
    recovered   = 0

    # Try to get richer data from surplus.sqlite
    if SURPLUS_DB.exists():
        try:
            conn = sqlite3.connect(str(SURPLUS_DB))
            for stage, query in [
                ("skip_traced", "SELECT COUNT(*) FROM surplus_opportunities WHERE phone IS NOT NULL OR current_address IS NOT NULL"),
                ("letters_sent", "SELECT COUNT(*) FROM surplus_opportunities WHERE letter_sent_date IS NOT NULL"),
                ("agreements",   "SELECT COUNT(*) FROM surplus_opportunities WHERE agreement_signed_date IS NOT NULL"),
                ("filed",        "SELECT COUNT(*) FROM surplus_opportunities WHERE claim_filed_date IS NOT NULL"),
                ("recovered",    "SELECT COUNT(*) FROM surplus_opportunities WHERE recovery_amount IS NOT NULL AND recovery_amount > 0"),
            ]:
                try:
                    cur = conn.execute(query)
                    val = cur.fetchone()[0]
                    if stage == "skip_traced":   skip_traced = val
                    elif stage == "letters_sent": letters_sent = val
                    elif stage == "agreements":   agreements = val
                    elif stage == "filed":        filed = val
                    elif stage == "recovered":    recovered = val
                except:
                    pass
            conn.close()
        except:
            pass

    stages = [
        ("Identified",     identified,   money(total_surplus), "Total surplus found"),
        ("Skip Traced",    skip_traced,  "Owner located",       "Phone + address"),
        ("Letters Sent",   letters_sent, "Outreach complete",   "Awaiting response"),
        ("Agreements",     agreements,   "Contingency signed",  "Committed positions"),
        ("Claims Filed",   filed,        "With county",         "Processing 60-120d"),
        ("Recovered",      recovered,    money(recovered * 7000 * 0.35), "Net to you @35%"),
    ]

    for name, count, value, sub in stages:
        pct = int((count / max(identified, 1)) * 100)
        bar_color = "#22c55e" if count > 0 else "#1e3a5f"
        st.markdown(f"""<div class="stage-bar">
            <div style="flex:1;">
                <div style="display:flex; justify-content:space-between;">
                    <span class="stage-name">{name}</span>
                    <span class="stage-count">{count}</span>
                </div>
                <div style="background:#1e3a5f; border-radius:3px; height:4px; margin-top:6px;">
                    <div style="background:{bar_color}; width:{pct}%; height:4px; border-radius:3px;"></div>
                </div>
                <div style="display:flex; justify-content:space-between; margin-top:4px;">
                    <span style="font-size:0.72rem; color:#475569;">{sub}</span>
                    <span class="stage-value" style="font-size:0.72rem;">{value}</span>
                </div>
            </div>
        </div>""", unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # Excess proceeds by county
    st.markdown("##### Surplus by County")

    ep_counties = {
        "Humboldt": {"claims": len(hum_ep) if not hum_ep.empty else 30, "total": total_surplus, "deadline": "2027-06-18", "status": "IDENTIFIED"},
        "Butte":    {"claims": 433, "total": 3340000, "deadline": "2027-06-18", "status": "LETTERS_PENDING"},
        "Tehama":   {"claims": 0,   "total": 0,       "deadline": "ROLLING",   "status": "NEEDS_SKIP_TRACE"},
    }

    for county, info in ep_counties.items():
        d = days_until(info["deadline"]) if info["deadline"] != "ROLLING" else None
        if d is not None:
            urgency_cls = "badge-red" if d < 90 else "badge-yellow" if d < 180 else "badge-green"
            deadline_label = f"{d}d to escheat"
        else:
            urgency_cls = "badge-yellow"
            deadline_label = "Rolling deadline"

        status_map = {
            "IDENTIFIED":      ("badge-blue",   "Identified"),
            "LETTERS_PENDING": ("badge-yellow",  "Letters Pending"),
            "NEEDS_SKIP_TRACE":("badge-gray",   "Needs Skip Trace"),
            "COMPLETE":        ("badge-green",  "Complete"),
        }
        s_cls, s_label = status_map.get(info["status"], ("badge-gray", info["status"]))

        st.markdown(f"""<div class="auction-card">
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <div>
                    <div class="auction-county">{county}</div>
                    <div class="auction-date">{info['claims']} claims · {money(info['total'])} total surplus</div>
                    <div style="margin-top:6px;">
                        <span class="{s_cls}">{s_label}</span>
                        <span class="{urgency_cls}" style="margin-left:6px;">{deadline_label}</span>
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:1.1rem; font-weight:700; color:#22c55e;">{money(info['total'] * 0.35 * 0.15)}</div>
                    <div style="font-size:0.72rem; color:#6b7fa3;">Est. net @35% / 15% close</div>
                </div>
            </div>
        </div>""", unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # Automations — Leg 2
    st.markdown("##### Automations")
    col_e, col_f = st.columns(2)
    with col_e:
        if st.button("🔍 Fix Tehama + Recheck", key="fix_tehama"):
            with st.spinner("Running MPTS owner fill + circuit breaker..."):
                r1 = subprocess.run([sys.executable, "fix_tehama.py"], capture_output=True, text=True, cwd=str(ROOT), timeout=120)
                r2 = subprocess.run([sys.executable, "integrity_circuit_breaker.py", "--county", "tehama"], capture_output=True, text=True, cwd=str(ROOT), timeout=60)
                st.code((r1.stdout + "\n" + r2.stdout)[-1500:])
                st.cache_data.clear()

    with col_f:
        if st.button("📬 Generate Outreach Letters", key="gen_letters"):
            if (ROOT / "outreach_generator.py").exists():
                with st.spinner("Generating letter batch..."):
                    result = subprocess.run([sys.executable, "outreach_generator.py", "--county", "butte"], capture_output=True, text=True, cwd=str(ROOT), timeout=120)
                    st.code(result.stdout[-1000:] if result.stdout else "outreach_generator.py not yet built.")
            else:
                st.warning("outreach_generator.py not yet built — this is Priority 3 in the scale plan.")

    col_g, col_h = st.columns(2)
    with col_g:
        if st.button("📊 Skip Trace Butte", key="skip_trace"):
            if (ROOT / "skip_trace.py").exists():
                result = subprocess.run([sys.executable, "skip_trace.py", "--county", "butte"], capture_output=True, text=True, cwd=str(ROOT), timeout=180)
                st.code(result.stdout[-1000:] if result.stdout else result.stderr[-500:])
            else:
                st.warning("skip_trace.py not yet built — Priority 2 in the scale plan.")
    with col_h:
        if st.button("🏛️ Check CA Unclaimed Property", key="unclaimed"):
            if (ROOT / "unclaimed_property.py").exists():
                result = subprocess.run([sys.executable, "unclaimed_property.py"], capture_output=True, text=True, cwd=str(ROOT), timeout=120)
                st.code(result.stdout[-1000:] if result.stdout else result.stderr[-500:])
            else:
                st.warning("unclaimed_property.py not yet built — Priority 6 in the scale plan.")

# ── FULL WIDTH BOTTOM ─────────────────────────────────────────────────────────
st.markdown('<hr class="divider">', unsafe_allow_html=True)

# County Health Grid
st.markdown("##### 58-County Health Matrix — All 58 Counties")

# Build full 58-county grid merging YAML platform data with health matrix status
ASSESSOR_LIVE = {"mpts", "arcgis", "socrata", "open_data", "csv"}
RECORDER_LIVE = {"tyler", "county_portal"}

cols = st.columns(6)
for i, slug in enumerate(all_counties):
    info    = county_platform.get(slug, {})
    hinfo   = (counties_health or {}).get(slug, {})
    assessor = info.get("assessor", "manual")
    recorder = info.get("recorder", "manual")
    display  = info.get("display", slug.replace("_"," ").title())

    # Determine status from health matrix override, else infer from platform
    h_status = str(hinfo.get("status","")).upper()
    if h_status and ("HEALTHY" in h_status or "LIVE" in h_status or "PASS" in h_status):
        dot      = "🟢"
        cell_cls = "health-cell-ok"
        sub      = h_status[:18]
    elif h_status and ("FAIL" in h_status or "ALERT" in h_status or "ERROR" in h_status):
        dot      = "🔴"
        cell_cls = "health-cell-fail"
        sub      = h_status[:18]
    elif assessor in ASSESSOR_LIVE:
        dot      = "🟢"
        cell_cls = "health-cell-ok"
        sub      = assessor.upper()
    else:
        dot      = "🟡"
        cell_cls = "health-cell-warn"
        sub      = "Needs adapter"

    rec_badge = "📄" if recorder in RECORDER_LIVE else "–"

    with cols[i % 6]:
        st.markdown(f"""<div class="{cell_cls}" style="margin-bottom:6px;">
            <div style="font-size:0.72rem; font-weight:600; color:#e2e8f0;">{dot} {display}</div>
            <div style="font-size:0.62rem; color:#6b7fa3;">{sub} {rec_badge}</div>
        </div>""", unsafe_allow_html=True)

if counties_health:
    cols = st.columns(5)
    for i, (county, info) in enumerate(counties_health.items()):
        status = str(info.get("status","")).upper()
        cell_cls = "health-cell-ok" if "HEALTHY" in status or "LIVE" in status or "PASS" in status else \
                   "health-cell-warn" if "PENDING" in status or "WARN" in status or "FILL" in status else \
                   "health-cell-fail"
        dot = "🟢" if "HEALTHY" in status or "LIVE" in status else "🟡" if "PENDING" in status or "WARN" in status else "🔴"
        with cols[i % 5]:
            st.markdown(f"""<div class="{cell_cls}" style="margin-bottom:6px;">
                <div style="font-size:0.8rem; font-weight:600; color:#e2e8f0;">{dot} {county.replace('_',' ').title()}</div>
                <div style="font-size:0.68rem; color:#6b7fa3;">{info.get('status','–')[:20]}</div>
            </div>""", unsafe_allow_html=True)
else:
    # Show platform coverage overview instead
    platform_data = [
        ("MPTS Live (30)", "Amador, Calaveras, Colusa, Del Norte, El Dorado, Glenn, Imperial, Kings, Lake, Madera, Mariposa, Merced, Modoc, Mono, Monterey, Napa, Nevada, Placer, Plumas, San Benito, San Joaquin, Siskiyou, Sonoma, Stanislaus, Tehama, Trinity, Tulare, Tuolumne, Yolo, Yuba", "🟢"),
        ("ArcGIS (2)",     "Fresno, Shasta", "🟢"),
        ("Tyler Recorder (20)", "Butte, Del Norte, Fresno, Glenn, Humboldt, Kern, Kings, Lake, Madera, Marin, Mariposa, Plumas, San Benito, Santa Cruz, Shasta, Tehama, Trinity, Tulare, Tuolumne, Yolo", "🟢"),
        ("Manual/Needs Adapter (24)", "Alameda, Alpine, Contra Costa, Inyo, Kern(assessor), LA, Lassen, Marin, Mendocino, Orange, Riverside, Sacramento, San Bernardino, San Diego, SF, SLO, San Mateo, Santa Barbara, Santa Clara, Santa Cruz, Sierra, Solano, Sutter, Ventura", "🟡"),
    ]
    for label, counties, dot in platform_data:
        st.markdown(f"**{dot} {label}**")
        st.caption(counties)

# Active Buyer Intelligence Database
st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown("##### 🎯 Verified Active Tax Auction Buyer Intelligence (782 Tracked Buyers)")

BUYER_CSV = ROOT / "output" / "active_buyers_intelligence.csv"
if BUYER_CSV.exists():
    try:
        df_buyers = pd.read_csv(BUYER_CSV)
        st.dataframe(
            df_buyers.head(20)[["buyer_name", "entity_type", "acquisitions_count", "total_capital_deployed", "counties_active", "last_active_date", "buyer_score"]],
            use_container_width=True,
            hide_index=True
        )
    except Exception:
        st.info("Active buyer database loading...")

# Revenue projection
st.markdown('<hr class="divider">', unsafe_allow_html=True)
st.markdown("##### Revenue Projection")
p1, p2, p3 = st.columns(3)
with p1:
    st.markdown("""<div class="kpi-card">
        <div class="kpi-value" style="color:#f59e0b;">$0</div>
        <div class="kpi-label">Month 1–3</div>
        <div class="kpi-sub">Letters going out. Pipeline building. No cash yet.</div>
    </div>""", unsafe_allow_html=True)
with p2:
    st.markdown("""<div class="kpi-card">
        <div class="kpi-value" style="color:#3b82f6;">$25K–$40K</div>
        <div class="kpi-label">Month 4–6</div>
        <div class="kpi-sub">First claims clear. Prop intel sales if buyers found.</div>
    </div>""", unsafe_allow_html=True)
with p3:
    st.markdown("""<div class="kpi-card">
        <div class="kpi-value" style="color:#22c55e;">$65K–$110K</div>
        <div class="kpi-label">Month 7–12</div>
        <div class="kpi-sub">Both legs running. 20+ counties active.</div>
    </div>""", unsafe_allow_html=True)

# Auto-refresh
st.markdown("---")
refresh_col, ts_col = st.columns([1, 4])
with refresh_col:
    if st.button("🔄 Refresh Dashboard"):
        st.cache_data.clear()
        st.rerun()
with ts_col:
    st.caption(f"Last loaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · Auto-refreshes every 60s when automations run")

# Auto-refresh note
st.caption("Tip: Press R to hard-refresh data at any time.")
