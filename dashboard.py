COUNTY_CONFIG = {
    "tehama": {
        "csv": "tax_pipeline/tehama_MASTER_leads_with_liens.csv",
        "lead_prefix": "Tehama_",
        "recorder_base": "https://recordsearch.tehama.gov/web/action/ACTIONGROUP200S1",
        "recorder_search": "https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1",
        "mpts_base": "https://common1.mptsweb.com/MBC/tehama/tax/main",
    },
    "shasta": {
        "csv": "tax_pipeline/shasta_MASTER_leads_with_liens.csv",
        "lead_prefix": "Shasta_",
        "recorder_base": "https://eagleweb.co.shasta.ca.us/eaglesoftware/web/action/ACTIONGROUP200S1",
        "recorder_search": "https://eagleweb.co.shasta.ca.us/eaglesoftware/web/search/DOCSEARCH4S1",
        "mpts_base": "https://common2.mptsweb.com/MBC/shasta/tax/main",
    },
}

import streamlit as st
import pandas as pd
import numpy as np
import os
import re
import sqlite3
from datetime import datetime
from urllib.parse import quote, quote_plus

def normalize_apn(apn: str) -> str:
    return re.sub(r"\D", "", apn or "")

def build_parcel_url(apn: str, tax_year) -> str | None:
    compact = normalize_apn(apn)
    if len(compact) != 12:
        return None
    year = str(tax_year or 2025)
    return f"https://common1.mptsweb.com/MBC/tehama/tax/main/{compact}/{year}/0000"

def parse_owner_name(raw_name: str) -> dict:
    raw = (raw_name or "").strip()
    if not raw:
        return {
            "raw": "",
            "first_name": None,
            "middle_name": None,
            "last_name": None,
            "is_multi_party": False,
            "is_entity": False,
            "is_trust": False,
            "type": "missing",
        }

    upper = raw.upper()
    is_entity = bool(re.search(r"\b(LLC|INC|CORP|LTD|LP|LLP|CO|COMPANY)\b", upper))
    is_trust = bool(re.search(r"\b(TRUST|TR|REVOC|FAMILY TRUST|LIVING TRUST|ESTATE)\b", upper))
    is_multi_party = bool(re.search(r"&|/|\bAND\b", upper))

    if "," in raw:
        last_part, right = [p.strip() for p in raw.split(",", 1)]
        tokens = [t for t in re.split(r"\s+", right) if t]
        first_name = tokens[0] if tokens else None
        middle_name = " ".join(tokens[1:]) if len(tokens) > 1 else None
        owner_type = "entity" if is_entity else "trust" if is_trust else "person"
        return {
            "raw": raw,
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_part,
            "is_multi_party": is_multi_party,
            "is_entity": is_entity,
            "is_trust": is_trust,
            "type": owner_type,
        }

    owner_type = "entity" if is_entity else "trust" if is_trust else "unparsed"
    return {
        "raw": raw,
        "first_name": None,
        "middle_name": None,
        "last_name": raw,
        "is_multi_party": is_multi_party,
        "is_entity": is_entity,
        "is_trust": is_trust,
        "type": owner_type,
    }

def build_recorder_direct_url(owner: dict, county_cfg: dict | None = None) -> str | None:
    if not owner or not owner.get("last_name"):
        return None
    base = (county_cfg or COUNTY_CONFIG["tehama"])["recorder_base"]
    last_name = quote(owner["last_name"])
    first_name = quote(owner.get("first_name") or "")
    return f"{base}?lastName={last_name}&firstName={first_name}"

def build_wide_search_variants(owner: dict) -> list[dict]:
    if not owner or not owner.get("raw"):
        return []

    variants = []
    seen = set()

    def add_variant(label: str, last_name: str | None, first_name: str | None = ""):
        if not last_name:
            return
        key = (last_name.strip().upper(), (first_name or "").strip().upper())
        if key in seen:
            return
        seen.add(key)
        url = (
            "https://recordsearch.tehama.gov/web/action/ACTIONGROUP200S1"
            f"?lastName={quote(last_name.strip())}&firstName={quote((first_name or '').strip())}"
        )
        variants.append({
            "label": label,
            "last_name": last_name.strip(),
            "first_name": (first_name or "").strip(),
            "url": url,
        })

    add_variant("Exact parsed search", owner.get("last_name"), owner.get("first_name") or "")

    if owner.get("middle_name"):
        add_variant("Drop middle name", owner.get("last_name"), owner.get("first_name") or "")

    raw_upper = owner["raw"].upper()
    if owner.get("is_multi_party"):
        pieces = [p.strip() for p in re.split(r"&|/|\bAND\b", owner["raw"], flags=re.I) if p.strip()]
        for piece in pieces:
            parsed = parse_owner_name(piece if "," in piece else piece)
            add_variant(f"Co-owner: {piece}", parsed.get("last_name"), parsed.get("first_name") or "")

    if owner.get("is_entity") or owner.get("is_trust"):
        add_variant("Entity / trust name search", owner["raw"], "")

    return variants

def compute_confidence(parcel_situs_address: str | None,
                       ownership_conflict: bool = False,
                       possible_transfer: bool = False) -> tuple[str, str]:
    has_address = bool((parcel_situs_address or "").strip())
    if ownership_conflict:
        return ("Low", "Sold / transfer detected")
    if has_address and not possible_transfer:
        return ("High", "Parcel facts resolved and no transfer flag")
    if has_address and possible_transfer:
        return ("Medium", "Parcel facts resolved, recorder needs review")
    return ("Low", "No verified parcel address")


# Set Page Config
st.set_page_config(
    page_title="Distressed Property Intelligence",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_PATH = "tax_pipeline/cps1_outcomes.db"

# Custom CSS for Premium UI
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    h1, h2, h3 { font-weight: 800 !important; letter-spacing: -0.5px; }
    div[data-testid="metric-container"] {
        background: rgba(30, 30, 30, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 1rem 1.5rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        backdrop-filter: blur(10px);
        transition: transform 0.2s ease-in-out;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-2px);
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    thead tr th:first-child {display:none}
    tbody th {display:none}
    .stDataFrame { border-radius: 12px; overflow: hidden; border: 1px solid rgba(255, 255, 255, 0.1); }
    [data-testid="stDeployButton"] { display: none !important; }
    [data-testid="stChatInput"] { display: none !important; }
    [data-testid="stAppViewBlockContainer"] { padding-bottom: 3rem !important; }
</style>
""", unsafe_allow_html=True)

def sync_to_db(df):
    """Sync the loaded leads and scores to the CPS-1 SQLite database."""
    if not os.path.exists(DB_PATH):
        return # DB not initialized yet
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Track the latest snapshot per lead so we can map it to events
    snapshot_map = {}
    
    for _, row in df.iterrows():
        lead_id = f"{row['County']}_{row['APN']}"
        
        # 1. Sync Lead
        cursor.execute('''
            INSERT OR IGNORE INTO leads (lead_id, county, apn, owner_name, address)
            VALUES (?, ?, ?, ?, ?)
        ''', (lead_id, row['County'], row['APN'], row['Owner'], row['Address']))
        
        # 2. Sync Score Snapshot (Only if it changed from the last snapshot, or just insert always? For V1, insert if not exists for today)
        cursor.execute('''
            SELECT snapshot_id, score FROM score_snapshots 
            WHERE lead_id = ? ORDER BY calculated_at DESC LIMIT 1
        ''', (lead_id,))
        last_snap = cursor.fetchone()
        
        if last_snap is None or last_snap[1] != row['Opportunity Score']:
            cursor.execute('''
                INSERT INTO score_snapshots (lead_id, score, score_reason)
                VALUES (?, ?, ?)
            ''', (lead_id, int(row['Opportunity Score']), row['Score Reason']))
            snapshot_map[lead_id] = cursor.lastrowid
        else:
            snapshot_map[lead_id] = last_snap[0]
            
    conn.commit()
    conn.close()
    return snapshot_map

def load_outcomes():
    """Fetch the latest outcome for each lead."""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame(columns=["lead_id", "Last Action", "Notes"])
        
    conn = sqlite3.connect(DB_PATH)
    df_outcomes = pd.read_sql_query('''
        SELECT 
            lead_id,
            outcome_tag as "Last Action",
            notes as "Notes"
        FROM outcome_events
        GROUP BY lead_id
        HAVING event_time = MAX(event_time)
    ''', conn)
    conn.close()
    return df_outcomes

def log_event(lead_id, snapshot_id, tag, notes, wholesaler):
    """Write a new interaction to the outcome_events log."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO outcome_events (lead_id, snapshot_id, outcome_tag, wholesaler_name, notes)
        VALUES (?, ?, ?, ?, ?)
    ''', (lead_id, snapshot_id, tag, wholesaler, notes))
    conn.commit()
    conn.close()

def load_verifications():
    """Fetch the latest verification for each lead."""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame(columns=["lead_id", "Verification Status", "Verification Notes"])
        
    conn = sqlite3.connect(DB_PATH)
    try:
        df_verif = pd.read_sql_query('''
            SELECT 
                lead_id,
                verification_status as "Verification Status",
                notes as "Verification Notes"
            FROM verification_events
            GROUP BY lead_id
            HAVING event_time = MAX(event_time)
        ''', conn)
    except sqlite3.OperationalError:
        # Table might not exist yet if init_db wasn't run
        df_verif = pd.DataFrame(columns=["lead_id", "Verification Status", "Verification Notes"])
    conn.close()
    return df_verif

def log_verification(lead_id, snapshot_id, status, notes, wholesaler):
    """Write a new interaction to the verification_events log."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO verification_events (lead_id, snapshot_id, verification_status, wholesaler_name, notes)
        VALUES (?, ?, ?, ?, ?)
    ''', (lead_id, snapshot_id, status, wholesaler, notes))
    conn.commit()
    conn.close()

def init_contact_table():
    """Ensure the lead_contacts table exists (idempotent)."""
    if not os.path.exists(DB_PATH):
        return
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS lead_contacts (
            contact_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id      TEXT NOT NULL,
            best_phone   TEXT DEFAULT '',
            phone_source TEXT DEFAULT 'manual',
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def load_phones():
    """Fetch the most recent phone entry per lead."""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame(columns=["lead_id", "best_phone", "phone_source"])
    conn = sqlite3.connect(DB_PATH)
    try:
        df_phones = pd.read_sql_query('''
            SELECT lead_id, best_phone, phone_source
            FROM lead_contacts
            GROUP BY lead_id
            HAVING updated_at = MAX(updated_at)
        ''', conn)
    except Exception:
        df_phones = pd.DataFrame(columns=["lead_id", "best_phone", "phone_source"])
    conn.close()
    return df_phones

def save_phone(lead_id, phone, source):
    """Insert or update the best phone for a lead."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO lead_contacts (lead_id, best_phone, phone_source) VALUES (?, ?, ?)',
        (lead_id, phone.strip(), source)
    )
    conn.commit()
    conn.close()

def load_contact_timeline(lead_id):
    """Return a unified chronological event log for a single lead."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute('''
            SELECT event_time, 'Verification' as kind, verification_status as action, notes
            FROM verification_events WHERE lead_id = ?
            UNION ALL
            SELECT event_time, 'Outreach' as kind, outcome_tag as action, notes
            FROM outcome_events WHERE lead_id = ?
            ORDER BY event_time DESC
        ''', (lead_id, lead_id)).fetchall()
    except Exception:
        rows = []
    conn.close()
    return rows

# Ensure phone table exists on every load
init_contact_table()

@st.cache_data(ttl=60)
def load_data(county_cfg: dict):
    file_path = county_cfg["csv"]
    if not os.path.exists(file_path):
        return pd.DataFrame(), {}
        
    df = pd.read_csv(file_path)
    df["County"] = county_cfg["lead_prefix"].replace("_", "")
    
    # Backfill missing mailing addresses for owners with multiple parcels
    df["mailing_address"] = df.groupby("assessee_name")["mailing_address"].transform(lambda x: x.ffill().bfill())
    
    # Vectorized String Operations for Motivation Signal
    mail = df["mailing_address"].fillna("").astype(str).str.upper()
    
    # Secure address fallback chain
    def clean_addr_series(col_name):
        series = df.get(col_name, pd.Series([np.nan]*len(df)))
        return series.replace({"": np.nan, "nan": np.nan, "NAN": np.nan, "None": np.nan})

    situs_pdf_clean = clean_addr_series("situs_pdf")
    address_clean = clean_addr_series("address")
    recorder_clean = clean_addr_series("recorder_situs")
    
    situs = (
        situs_pdf_clean
        .fillna(address_clean)
        .fillna(recorder_clean)
    )
    
    situs_upper = situs.astype(str).str.upper()
    owner_upper = df["assessee_name"].fillna("").astype(str).str.upper()

    # --- Ownership Type Detection (must run BEFORE geographic logic) ---
    # Corporate entities: LLC, INC, CORP, HOLDINGS, etc. — pure financial actors, faster decisions
    CORPORATE_MARKERS = ["LLC", "INC", "CORP", "CORPORATION", "HOLDINGS", "PROPERTIES",
                         "COMPANY", "CO", "SERVICES", "ASSOCIATION", "PARTNERSHIP", "LP", "LLP"]
    corporate_pattern = r'\b(' + '|'.join(CORPORATE_MARKERS) + r')\b'
    is_corporate = owner_upper.str.contains(corporate_pattern, regex=True)

    # Trust / Estate: family trusts, revocable trusts, estates — inherited/ambiguous ownership, slower to move
    TRUST_MARKERS = ["TRUST", "TR", "REVOC", "REVOCABLE", "ESTATE", "FAM", "FAMILY",
                     "TESTAMENTARY", "LIVING", "IRREVOCABLE"]
    trust_pattern = r'\b(' + '|'.join(TRUST_MARKERS) + r')\b'
    # is_trust = trust marker present AND not already classified as corporate
    is_trust = (~is_corporate) & owner_upper.str.contains(trust_pattern, regex=True)

    is_entity = is_corporate | is_trust  # either type = skip geographic fallthrough

    is_unknown = (~is_entity) & (mail.str.strip() == "")
    is_ca = mail.str.contains(r'\bCA\b|CALIFORNIA', regex=True)

    COUNTY_CITIES = {
        "Tehama": ["RED BLUFF", "CORNING", "LOS MOLINOS", "TEHAMA", "VINA", "PASKENTA", "FLOURNOY", "PROBERTA", "GERBER", "MINERAL", "PAYNES CREEK", "MANTON"]
    }
    tehama_pattern = "|".join([fr"\b{c}\b" for c in COUNTY_CITIES["Tehama"]])
    is_local = mail.str.contains(tehama_pattern, regex=True)

    is_po_box = mail.str.contains(r'P\s*O\s*BOX|POST OFFICE BOX', regex=True)
    mail_num = mail.str.extract(r'^(\d+)')[0]
    situs_num = situs_upper.str.extract(r'^(\d+)')[0]
    is_diff_street = (mail_num.notna()) & (situs_num.notna()) & (mail_num != situs_num)
    is_absentee = (~is_entity) & (is_po_box | is_diff_street)

    # Distressed Landlord signal from TylerTech
    is_assignment = df.get("has_assignment_of_rents", pd.Series([False]*len(df))) == True
    is_affidavit = df.get("has_affidavit_of_death", pd.Series([False]*len(df))) == True

    # Priority: Distressed Landlord > Probate > Corporate > Trust > Geographic
    conditions = [is_assignment, is_affidavit, is_corporate, is_trust, is_unknown, ~is_ca, ~is_local, is_absentee]
    choices = [
        "🎯 Distressed Landlord (Rents Assigned)",
        "👻 Probate / Estate",
        "🏢 Entity / LLC",        # Clean financial actor, fastest to move
        "🏛️ Trust / Estate",     # Inherited or wrapped ownership, slower
        "❓ Unknown",
        "🚨 High (Out-of-State)",
        "🔥 High (Non-Local CA)",
        "⚠️ Medium (Local Absentee)"
    ]
    df["Motivation Signal"] = np.select(conditions, choices, default="🧊 Low (Owner Occupied)")
    
    df["Owner"] = df["assessee_name"].fillna("Unknown").astype(str)
    raw_apn = df["apn_pdf"].fillna(df["fee_parcel"]).astype(str).str.replace(r"\.0$", "", regex=True)
    def fmt_apn(a):
        digits = re.sub(r"\D", "", a)
        if len(digits) == 12:
            return f"{digits[:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9:12]}"
        return a
    df["APN"] = raw_apn.apply(fmt_apn)
    if "live_tax_url" in df.columns:
        df["live_tax_url"] = df["live_tax_url"].where(df["live_tax_url"].notna(), None)
    
    # Generate lead_id
    df["lead_id"] = df["County"] + "_" + df["APN"]
    
    df["Balance_Val"] = pd.to_numeric(df["live_total_balance"], errors="coerce").fillna(0.0)
    df["Default Year"] = df["default_year"].fillna(df["earliest_year"]).fillna("Unknown")
    
    # --- Smooth Opportunity Score Engine ---
    score = np.zeros(len(df))
    
    score += np.where(df["Motivation Signal"] == "🚨 High (Out-of-State)", 25, 0)
    score += np.where(df["Motivation Signal"] == "🔥 High (Non-Local CA)", 15, 0)
    score += np.where(df["Motivation Signal"] == "⚠️ Medium (Local Absentee)", 10, 0)
    # Corporate entity: clean financial actor, no personal attachment = strong signal
    score += np.where(df["Motivation Signal"] == "🏢 Entity / LLC", 12, 0)
    # Trust/Estate: inherited ownership, slower to act = moderate positive signal
    score += np.where(df["Motivation Signal"] == "🏛️ Trust / Estate", 8, 0)
    
    current_year = 2026
    year_numeric = pd.to_numeric(df["Default Year"], errors='coerce').fillna(current_year)
    years_defaulted = np.where(df["Default Year"] != "Unknown", current_year - year_numeric, 0)
    
    score += np.where(years_defaulted >= 9, 15, 0)
    score += np.where((years_defaulted >= 7) & (years_defaulted < 9), 10, 0)
    score += np.where((years_defaulted >= 5) & (years_defaulted < 7), 5, 0)
    
    balance_points = np.clip((df["Balance_Val"] / 5000.0) * 50.0, 0, 50)
    score += balance_points
    
    # Boost score for Distressed Landlord signal
    score += np.where(df.get("has_assignment_of_rents", pd.Series([False]*len(df))) == True, 15, 0)
    
    # Boost score for Probate / Estate signal
    score += np.where(df.get("has_affidavit_of_death", pd.Series([False]*len(df))) == True, 10, 0)
    
    # (Score will be finalized after lien adjustment below)
    
    mot_reason = df["Motivation Signal"].str.split(" ", n=1).str[-1].str.replace(r'\(|\)', '', regex=True)
    age_reason = df["Default Year"].astype(str) + " Default"
    bal_reason = np.vectorize(lambda x: f"${x:,.0f} Bal")(df["Balance_Val"])
    df["Score Reason"] = mot_reason + " + " + age_reason + " + " + pd.Series(bal_reason)
    
    
    if "active_liens" not in df.columns:
        df["active_liens"] = 0
    if "mortgages" not in df.columns:
        df["mortgages"] = 0
        
    df["active_liens"] = df["active_liens"].fillna(0).astype(int)
    df["mortgages"] = df["mortgages"].fillna(0).astype(int)
    
    # Tiered Lien Scoring
    lien_score = np.zeros(len(df))
    
    cond_free_clear = (df["active_liens"] == 0) & (df["mortgages"] == 0)
    cond_mortgage_only = (df["active_liens"] == 0) & (df["mortgages"] > 0)
    cond_one_lien = (df["active_liens"] == 1)
    cond_multi_lien = (df["active_liens"] > 1)
    
    lien_score = np.where(cond_free_clear, 15, lien_score)
    lien_score = np.where(cond_mortgage_only, 5, lien_score)
    lien_score = np.where(cond_one_lien, -10, lien_score)
    lien_score = np.where(cond_multi_lien, -25, lien_score)
    
    df["Lien_Score"] = lien_score.astype(int)
    score += df["Lien_Score"]
    
    if "ownership_status" not in df.columns:
        df["ownership_status"] = "Current"
    df["ownership_status"] = df["ownership_status"].fillna("Current")
    
    # Preserve the original delinquency score (historical distress signal)
    # We no longer penalize the score for ownership conflicts. Instead, we suppress the tier.
    df["Opportunity Score"] = score.astype(int)
    
    df["Address"] = situs
    df["Default Balance"] = df["Balance_Val"].apply(lambda x: f"${x:,.2f}")
    df["Internal Opportunity Score"] = df["Opportunity Score"]
    
    # --- TIERING LOGIC ---
    tier1_cond = (df["Opportunity Score"] >= 50) & (df["Balance_Val"] >= 1000) & (df["active_liens"] == 0) & (df["ownership_status"] == "Current")
    tier2_cond = ((df["Opportunity Score"] >= 40) | (df["Balance_Val"] >= 300)) & ~tier1_cond & (df["ownership_status"] == "Current")
    
    df["Tier"] = np.where(tier1_cond, "Tier 1 (Acquisition Priority)", 
                 np.where(tier2_cond, "Tier 2 (Pipeline)", "Tier 3 (Noise/Conflict)"))
    
    # Map asrprint_url into live_tax_url for gold leads that don't have a live tax portal url
    if "live_tax_url" not in df.columns:
        df["live_tax_url"] = None
    if "asrprint_url" in df.columns:
        df["live_tax_url"] = df["live_tax_url"].fillna(df["asrprint_url"])
    

    # ── Equity Snapshot ─────────────────────────────────────────────
    # Parse the net_assessed_value string (e.g. '$60,339') into a float
    if "net_assessed_value" in df.columns:
        df["Assessed_Val"] = (
            df["net_assessed_value"]
            .astype(str)
            .str.replace(r"[$,]", "", regex=True)
            .str.strip()
            .pipe(pd.to_numeric, errors="coerce")
            .fillna(0.0)
        )
    else:
        df["Assessed_Val"] = 0.0

    df["Equity_Est"] = df["Assessed_Val"] - df["Balance_Val"]
    df["Assessed Value"] = df["Assessed_Val"].apply(
        lambda x: f"${x:,.0f}" if x > 0 else "N/A"
    )
    df["Equity Est"] = df["Equity_Est"].apply(
        lambda x: f"${x:,.0f}" if x != 0 else "N/A"
    )
    # Equity tier for color coding
    def equity_tier(eq, assessed):
        if assessed == 0:
            return "unknown"
        ratio = eq / assessed
        if ratio >= 0.6:
            return "strong"   # 60%+ equity
        elif ratio >= 0.3:
            return "moderate" # 30–60%
        elif ratio >= 0.0:
            return "thin"     # 0–30%
        else:
            return "negative" # underwater
    df["Equity_Tier"] = df.apply(
        lambda r: equity_tier(r["Equity_Est"], r["Assessed_Val"]), axis=1
    )
    # ───────────────────────────────────────────────

    # Sync to DB and get snapshot IDs
    snapshot_map = sync_to_db(df)
    
    # Join Outcomes
    outcomes_df = load_outcomes()
    if not outcomes_df.empty:
        df = df.merge(outcomes_df, on="lead_id", how="left")
    else:
        df["Last Action"] = "No Attempt Yet"
        df["Notes"] = ""
        
    df["Last Action"] = df["Last Action"].fillna("No Attempt Yet")
    df["Notes"] = df["Notes"].fillna("")
    
    # Join Verifications
    verifs_df = load_verifications()
    if not verifs_df.empty:
        df = df.merge(verifs_df, on="lead_id", how="left", suffixes=('_csv', '_db'))
        
        if "Verification Status_db" in df.columns:
            df["Verification Status"] = df["Verification Status_db"].fillna(df.get("Verification Status_csv", "Unverified"))
            df = df.drop(columns=["Verification Status_db", "Verification Status_csv"], errors="ignore")
        elif "Verification Status_csv" in df.columns:
            df["Verification Status"] = df["Verification Status_csv"]
            df = df.drop(columns=["Verification Status_csv"])
            
        if "Verification Notes_db" in df.columns:
            df["Verification Notes"] = df["Verification Notes_db"].fillna(df.get("Verification Notes_csv", ""))
            df = df.drop(columns=["Verification Notes_db", "Verification Notes_csv"], errors="ignore")
        elif "Verification Notes_csv" in df.columns:
            df["Verification Notes"] = df["Verification Notes_csv"]
            df = df.drop(columns=["Verification Notes_csv"])
    else:
        if "Verification Status" not in df.columns:
            df["Verification Status"] = df.get("verification_status", "Unverified")
        if "Verification Notes" not in df.columns:
            df["Verification Notes"] = ""
            
    df["Verification Status"] = df["Verification Status"].fillna("Unverified")
    df["Verification Notes"] = df["Verification Notes"].fillna("")

    # Join Phones
    phones_df = load_phones()
    if not phones_df.empty:
        df = df.merge(phones_df, on="lead_id", how="left")
    else:
        df["best_phone"] = ""
        df["phone_source"] = ""
    df["best_phone"] = df["best_phone"].fillna("")
    df["phone_source"] = df["phone_source"].fillna("")

    return df, snapshot_map

# Header
st.title("Distressed Property Intelligence")
st.markdown("<p style='color: #888; font-size: 1.1rem;'>Verified tax-delinquent property leads with live balances and owner-location flags.</p>", unsafe_allow_html=True)
st.divider()

col1, col2 = st.columns([1, 2])

with col1:
    selected_county = st.selectbox(
        "Select County Data Source",
        options=list(COUNTY_CONFIG.keys()),
        format_func=lambda x: x.capitalize(),
        index=0,
        key="main_county_selector"
    )

ACTIVE_COUNTY = COUNTY_CONFIG[selected_county]

with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(f"🚀 Run Extraction for {selected_county.capitalize()} (20-30m)", use_container_width=True, type="primary"):
        import subprocess
        import time
        with st.status(f"Extracting {selected_county.capitalize()} data...", expanded=True) as status:
            st.write("Initializing pipeline... this will take ~20-30 minutes.")
            log_placeholder = st.empty()
            
            # Start process without a window, capturing output
            process = subprocess.Popen(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", ".\\run_all.ps1", selected_county],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            
            # Stream output to the dashboard
            log_lines = []
            for line in iter(process.stdout.readline, ''):
                if line:
                    log_lines.append(line.strip())
                    # Display the last 15 lines of output so the UI doesn't crash from huge logs
                    log_placeholder.code("\n".join(log_lines[-15:]), language="text")
            
            process.stdout.close()
            return_code = process.wait()
            
            if return_code == 0:
                status.update(label="Extraction Complete!", state="complete", expanded=False)
                st.success("Extraction finished successfully. Reloading dashboard...")
                time.sleep(2)
                st.rerun()
            else:
                status.update(label="Extraction Failed!", state="error", expanded=True)
                st.error("Pipeline exited with an error. Please check the logs.")

st.divider()

# Filter Sidebar
st.sidebar.header("Filter Leads")

# Load Data
df, snapshot_map = load_data(ACTIVE_COUNTY)

if df.empty:
    st.error(f"No enriched master leads file found for {selected_county.capitalize()}. Click 'Run Extraction' in the sidebar to build it.")
    st.stop()


min_score = st.sidebar.slider("Minimum Opportunity Score", min_value=0, max_value=100, value=0, step=5)

max_bal = float(df["Balance_Val"].max())
min_bal = float(df["Balance_Val"].min())
if max_bal > min_bal:
    bal_filter = st.sidebar.slider("Minimum Default Balance", min_value=0.0, max_value=max_bal, value=0.0, step=100.0)
else:
    bal_filter = 0.0

all_signals = df["Motivation Signal"].unique().tolist()
signal_filter = st.sidebar.multiselect("Motivation Signal", options=all_signals, default=all_signals)

years = sorted([str(y) for y in df["Default Year"].unique() if y != "Unknown"])
if "Unknown" in df["Default Year"].unique():
    years.append("Unknown")
year_filter = st.sidebar.multiselect("Default Year", options=years, default=years)

# Filter: Verification Status (primary workflow gate)
VERIF_STATUS_OPTIONS = ["Unverified", "Verified", "Needs Review", "Disqualified"]
verif_filter = st.sidebar.multiselect(
    "Verification Status",
    options=VERIF_STATUS_OPTIONS,
    default=["Unverified", "Verified", "Needs Review"],
    help="Filter by where leads are in the verification workflow. Hide Disqualified to keep your queue clean."
)

# Filter: Action Status (only relevant after verification)
status_options = ["No Attempt Yet", "Attempted Contact", "Spoke to Owner", "Warm / Interested", "Bad Contact / Wrong Owner", "Not Interested", "Offer Made", "Deal Closed"]
status_filter = st.sidebar.multiselect("Outreach Status", options=status_options, default=status_options)

search_filter = st.sidebar.text_input("Search Owner Name or APN")

st.sidebar.divider()
tier_filter = st.sidebar.radio("Lead Segment", ["Tier 1 Only", "Tier 2 Only", "All Leads"])

# Apply Filters
filtered_df = df[
    (df["Opportunity Score"] >= min_score) &
    (df["Balance_Val"] >= bal_filter) &
    (df["Motivation Signal"].isin(signal_filter)) &
    (df["Default Year"].astype(str).isin(year_filter)) &
    (df["Last Action"].isin(status_filter)) &
    (df["Verification Status"].isin(verif_filter))
]

if tier_filter == "Tier 1 Only":
    filtered_df = filtered_df[filtered_df["Tier"] == "Tier 1 (Acquisition Priority)"]
elif tier_filter == "Tier 2 Only":
    filtered_df = filtered_df[filtered_df["Tier"] == "Tier 2 (Pipeline)"]

if search_filter:
    term = search_filter.lower()
    filtered_df["_search_match"] = filtered_df["Owner"].str.lower().str.contains(term, regex=False) | filtered_df["APN"].str.lower().str.contains(term, regex=False)
else:
    filtered_df["_search_match"] = True

# Sort: Verified leads bubble up within each score tier, Disqualified sink
verif_sort_order = {"Verified": 0, "Needs Review": 1, "Unverified": 2, "Disqualified": 3}
filtered_df["_verif_sort"] = filtered_df["Verification Status"].map(verif_sort_order).fillna(2)
filtered_df = filtered_df.sort_values(
    by=["_search_match", "Opportunity Score", "_verif_sort", "Balance_Val"],
    ascending=[False, False, True, False]
).drop(columns=["_verif_sort", "_search_match"]).reset_index(drop=True)

# KPIs
col1, col2, col3, col4, col5 = st.columns(5)
total_parcels = len(filtered_df)
unique_owners = filtered_df["Owner"].nunique() if total_parcels > 0 else 0
total_capital = filtered_df["Balance_Val"].sum()
high_motivation_count = len(filtered_df[filtered_df["Motivation Signal"].isin([
    "🚨 High (Out-of-State)", "🔥 High (Non-Local CA)", "🏢 Entity / LLC", "🏛️ Trust / Estate"
])])
verified_count = len(filtered_df[filtered_df["Verification Status"] == "Verified"])
unverified_count = len(filtered_df[filtered_df["Verification Status"].isin(["Unverified", "Needs Review"])])

with col1:
    st.metric("Total Parcels", f"{total_parcels:,}")
with col2:
    st.metric("Total Capital in Default", f"${total_capital:,.2f}")
with col3:
    st.metric("High Motivation", f"{high_motivation_count:,}")
with col4:
    st.metric("✅ Verified", f"{verified_count:,}")
with col5:
    st.metric("🔲 Awaiting Review", f"{unverified_count:,}")

st.caption(f"Viewing **{unique_owners} unique owners** across **{total_parcels} parcels** — **{verified_count} verified** and ready for outreach, **{unverified_count} awaiting review**.")
st.markdown("<br>", unsafe_allow_html=True)

# Data Table & Data Editor
st.subheader("Ranked Opportunity Pipeline")
st.markdown("<p style='color: #888; font-size: 0.95rem; margin-top: -10px;'>Top-ranked leads prioritize absentee ownership, older defaults, and larger balances.</p>", unsafe_allow_html=True)

if total_parcels == 0:
    st.info("No leads match your current filter criteria. Try adjusting the Opportunity Score or Motivation filters in the sidebar.")
else:
    display_cols = [
        "Opportunity Score", "Last Action", "Notes", "Owner", "APN", "Address",
        "Default Year", "Motivation Signal", "Default Balance", "Score Reason",
        "live_tax_url", "lead_id",
        "active_liens", "mortgages", "Tier", "ownership_status",
        "Verification Status", "Verification Notes",
        "Assessed Value", "Equity Est", "Equity_Tier", "Equity_Est",
        "best_phone", "phone_source"
    ]
    display_df = filtered_df[display_cols].copy()
    
    # Render Custom Cards instead of 1990s spreadsheet
    for idx, row in display_df.iterrows():
        # Title of the expander: Rank | Score | Owner | Balance | Verification Status
        tier_emoji = "🏆" if "Tier 1" in row['Tier'] else ("🎯" if "Tier 2" in row['Tier'] else "🧊")
        if row['ownership_status'] == "Sold / Transfer Detected":
            tier_emoji = "🚫"

        # Verification badge in title
        verif_status = row['Verification Status']
        verif_badge_map = {
            "Verified":      "✅ Verified",
            "Needs Review":  "🔍 Needs Review",
            "Disqualified":  "🚫 Disqualified",
            "Unverified":    "🔲 Unverified",
        }
        verif_badge = verif_badge_map.get(verif_status, "🔲 Unverified")
        
        ownership_conflict = (row.get('ownership_status') == "Sold / Transfer Detected")
        possible_transfer = (row.get('ownership_status') == "Possible Transfer")
        
        # --- OVERRIDE: Check manual Verification Notes for transfer discoveries ---
        verif_notes = str(row.get('Verification Notes', '')).strip()
        new_owner_candidate = None
        notes_lower = verif_notes.lower()
        # Only trigger on affirmative transfer language, not negations
        has_transfer_signal = bool(re.search(
            r'(?<!no\s)(?<!not\s)(?<!no\s\w\s)(?:transferred to|sold to|new owner is|deed transferred|ownership changed|conveyed to)',
            notes_lower
        ))
        if has_transfer_signal:
            ownership_conflict = True
            m = re.search(r'(?:transferred to|new owner is|sold to|conveyed to)\s+([A-Za-z\s\-\']+)(?:\s+in\s+|\.|$|,)', verif_notes, flags=re.IGNORECASE)
            if m:
                new_owner_candidate = m.group(1).strip()
        
        if ownership_conflict or possible_transfer:
            display_owner = new_owner_candidate if new_owner_candidate else f"Former: {row['Owner']}"
        else:
            display_owner = row['Owner']
            
        expander_title = f"{tier_emoji} Rank {idx+1} | Score: {row['Opportunity Score']} | {display_owner} | {row['Default Balance']} | {verif_badge}"
        with st.expander(expander_title, expanded=(idx == 0)):
            if ownership_conflict or possible_transfer:
                st.error("🚫 **OWNERSHIP CONFLICT:** This owner has conveyed the title. Suppressed from outreach until verified.")
                
            parsed_owner = parse_owner_name(str(row.get('assessee_name', '')))
            direct_url = build_recorder_direct_url(parsed_owner, ACTIVE_COUNTY)
            wide_urls = build_wide_search_variants(parsed_owner)
            
            # Use year from lead if possible, else 2025
            dy = str(row.get('Default Year', '')).strip()
            tax_year = dy if dy.isdigit() else "2025"
            parcel_url = build_parcel_url(row['APN'], tax_year)
            
            raw_addr = str(row['Address']).strip()
            # Clean up the literal " City" artifact from the Tehama assessor portal
            raw_addr = re.sub(r'(?i)\s+City\s*$', '', raw_addr)
            
            has_addr = raw_addr and raw_addr.upper() not in ["NAN", "NONE", "", "SEE ASSESSOR", "SEE ASSESSOR →"]
            conf_level, conf_reason = compute_confidence(raw_addr if has_addr else None, ownership_conflict, possible_transfer)

            # Top row: 3 Layers
            layer1, layer2, layer3 = st.columns(3)
            with layer1:
                st.markdown("#### 1. Ranked Parcel")
                if ownership_conflict or possible_transfer:
                    st.markdown(f"**Former Owner:** `{row['Owner']}`")
                    if new_owner_candidate:
                        st.markdown(f"**Current Candidate:** `{new_owner_candidate}`")
                else:
                    st.markdown(f"**Owner:** `{row['Owner']}`")
                
                parsed_str = ""
                if parsed_owner.get('first_name'):
                    parsed_str += f"{parsed_owner['first_name']} "
                if parsed_owner.get('last_name'):
                    parsed_str += parsed_owner['last_name']
                st.markdown(f"**Parsed:** `{parsed_str}`")
                st.markdown(f"**Default Year:** `{row['Default Year']}`")
                st.markdown(f"**Original Score:** `{row['Opportunity Score']}`")
                st.markdown(f"**Signal:** {row['Motivation Signal']}")
                
                eq_tier = row.get('Equity_Tier', 'unknown')
                eq_val  = str(row.get('Equity Est', 'N/A')).replace('$', '&#36;')
                av_val  = str(row.get('Assessed Value', 'N/A')).replace('$', '&#36;')
                eq_badge_html = {
                    "strong":   f"<span style='background:#1a4731;color:#4ade80;padding:3px 10px;border-radius:6px;font-weight:700;'>&#x1F4B0; Strong Equity &mdash; {eq_val} est. ({av_val} assessed)</span>",
                    "moderate": f"<span style='background:#1c3a5e;color:#60a5fa;padding:3px 10px;border-radius:6px;font-weight:700;'>&#x1F4CA; Moderate Equity &mdash; {eq_val} est. ({av_val} assessed)</span>",
                    "thin":     f"<span style='background:#3b2f0a;color:#fbbf24;padding:3px 10px;border-radius:6px;font-weight:700;'>&#x26A0;&#xFE0F; Thin Equity &mdash; {eq_val} est. ({av_val} assessed)</span>",
                    "negative": f"<span style='background:#3b0a0a;color:#f87171;padding:3px 10px;border-radius:6px;font-weight:700;'>&#x1F534; Negative Equity &mdash; {eq_val} est. ({av_val} assessed)</span>",
                    "unknown":  f"<span style='background:#1e1e1e;color:#9ca3af;padding:3px 10px;border-radius:6px;font-weight:700;'>&#x2753; Equity Unknown (no assessed value on file)</span>",
                }.get(eq_tier, "")
                st.markdown(eq_badge_html, unsafe_allow_html=True)

            with layer2:
                st.markdown("#### 2. Parcel Facts")
                st.markdown(f"**APN:** `{row['APN']}`")
                st.markdown(f"**Address:** `{raw_addr if has_addr else 'Missing'}`")
                
                doc_num = row.get("rec_doc_number", "N/A")
                if pd.isna(doc_num): doc_num = "N/A"
                st.markdown(f"**Document Number:** `{doc_num}`")
                st.markdown(f"**Tax Year:** `{tax_year}`")
                
                if parcel_url:
                    st.markdown(f"👉 [**View MPTS Parcel Page**]({parcel_url})")
                
                live_tax_url = str(row.get('live_tax_url', '')).strip()
                if live_tax_url and live_tax_url.lower() not in {"nan", "none", "<na>", ""}:
                    st.markdown(f"👉 [**Assessor Property Detail**]({live_tax_url})")

                if has_addr:
                    map_q = quote_plus(f"{raw_addr}, Tehama County, CA")
                    st.markdown(f"📍 [**Google Maps**](https://maps.google.com/?q={map_q})")

            with layer3:
                st.markdown("#### 3. Recorder Findings")
                
                if ownership_conflict or possible_transfer:
                    st.error("🚫 **Ownership Conflict:** Transfer detected")
                    if new_owner_candidate:
                        st.markdown(f"**Current owner candidate:** `{new_owner_candidate}`")
                        new_parsed = parse_owner_name(new_owner_candidate)
                        new_direct = build_recorder_direct_url(new_parsed, ACTIVE_COUNTY)
                        if new_direct:
                            st.markdown(f"👉 [**Recorder Search: Pre-filled for new owner**]({new_direct})")
                        else:
                            st.markdown(f"👉 [**Recorder Search (Manual Name Entry)**]({ACTIVE_COUNTY['recorder_search']})")
                    else:
                        st.markdown(f"👉 [**Recorder Search (Manual Name Entry)**]({ACTIVE_COUNTY['recorder_search']})")
                        
                    with st.expander("Original Owner Links"):
                        if direct_url:
                            st.markdown(f"👉 [**Recorder Search (Direct)**]({direct_url})")
                        if wide_urls:
                            for v in wide_urls:
                                st.markdown(f"🔍 [{v['label']}]({v['url']})")
                else:
                    if conf_level == "High":
                        st.success(f"**High Confidence:** {conf_reason}")
                    elif conf_level == "Medium":
                        st.warning(f"**Medium Confidence:** {conf_reason}")
                    else:
                        st.error(f"**Low Confidence:** {conf_reason}")

                    if direct_url:
                        st.markdown(f"👉 [**Recorder Search (Direct)**]({direct_url})")
                    else:
                        st.markdown("👉 **Recorder Search:** Unavailable")

                    if wide_urls:
                        with st.expander("Wide Search Variants"):
                            for v in wide_urls:
                                st.markdown(f"🔍 [{v['label']}]({v['url']})")

                active_liens = int(row.get("active_liens", 0))
                mortgages = int(row.get("mortgages", 0))
                if active_liens > 0:
                    st.error(f"🔴 **High Risk:** {active_liens} Active Lien(s) found on title")
                elif mortgages > 0:
                    st.warning(f"🟡 **Medium Risk:** {mortgages} Mortgage(s) / Deed(s) of Trust found")
                else:
                    st.success("🟢 **Clear:** No recorded liens or mortgages detected")
            
            st.divider()
            
            # Bottom row: Form
            with st.container():
                # ── STEP 1: VERIFICATION ───────────────────────────────────
                verif_options = ["Unverified", "Verified", "Needs Review", "Disqualified"]
                curr_verif = row['Verification Status']
                v_idx = verif_options.index(curr_verif) if curr_verif in verif_options else 0

                # Current verification status callout
                verif_callout = {
                    "Verified":     ("success", "✅ **Verified** — Ownership confirmed. Outreach is unlocked."),
                    "Needs Review": ("warning", "🔍 **Needs Review** — Complete verification before initiating outreach."),
                    "Disqualified": ("error",   "🚫 **Disqualified** — This lead has been removed from the outreach queue."),
                    "Unverified":   ("info",     "🔲 **Unverified** — Confirm ownership, title status, and delinquency before calling."),
                }
                callout_type, callout_msg = verif_callout.get(curr_verif, ("info", "🔲 Unverified"))

                st.markdown("### Step 1: Verification")
                getattr(st, callout_type)(callout_msg)

                # Phone capture (outside the verif form so it saves independently)
                curr_phone = str(row.get('best_phone', '') or '')
                curr_source = str(row.get('phone_source', 'manual') or 'manual')
                with st.form(key=f"phone_form_{row['lead_id']}"):
                    ph_col1, ph_col2 = st.columns([2, 1])
                    with ph_col1:
                        new_phone = st.text_input(
                            "&#x1F4DE; Best Phone Number",
                            value=curr_phone,
                            placeholder="e.g. (530) 555-1234",
                            key=f"phone_input_{row['lead_id']}"
                        )
                    with ph_col2:
                        src_options = ["manual", "skip_trace", "owner_provided", "relative"]
                        src_idx = src_options.index(curr_source) if curr_source in src_options else 0
                        new_src = st.selectbox("Source", options=src_options, index=src_idx, key=f"src_select_{row['lead_id']}")
                    save_ph = st.form_submit_button("&#x1F4BE; Save Phone", type="secondary")
                    if save_ph and new_phone.strip():
                        save_phone(row['lead_id'], new_phone, new_src)
                        st.cache_data.clear()
                        st.rerun()

                with st.form(key=f"verif_form_{row['lead_id']}"):
                    new_verif = st.selectbox(
                        "Update Verification Status",
                        options=verif_options,
                        index=v_idx,
                        help="Verified = current owner confirmed, title is workable, delinquency is real. Disqualified = do not contact.",
                        key=f"verif_select_{row['lead_id']}"
                    )
                    new_v_notes = st.text_area(
                        "Verification Notes",
                        value=row['Verification Notes'] if pd.notna(row['Verification Notes']) else "",
                        height=80,
                        placeholder="e.g. Confirmed owner via Recorder deed 2023. No active liens. Ready to contact.",
                        key=f"verif_notes_{row['lead_id']}"
                    )
                    submit_verif = st.form_submit_button("💾 Save Verification", type="primary")
                    if submit_verif:
                        snap_id = snapshot_map.get(row['lead_id'])
                        log_verification(row['lead_id'], snap_id, new_verif, new_v_notes, "Internal Wholesaler")
                        st.cache_data.clear()
                        st.rerun()

                st.divider()

                # ── STEP 2: OUTREACH (gated on Verified status) ────────────
                st.markdown("### Step 2: Outreach")
                if curr_verif == "Verified":
                    curr_status = row['Last Action']
                    status_idx = status_options.index(curr_status) if curr_status in status_options else 0
                    if curr_status != "No Attempt Yet":
                        st.info(f"📋 Last logged action: **{curr_status}**" + (f" — _{row['Notes']}_" if row['Notes'] else ""))
                    with st.form(key=f"outreach_form_{row['lead_id']}"):
                        new_status = st.selectbox("Outreach Status", options=status_options, index=status_idx, key=f"outreach_select_{row['lead_id']}")
                        new_notes = st.text_area(
                            "Outreach Notes",
                            value=row['Notes'] if pd.notna(row['Notes']) else "",
                            height=80,
                            placeholder="e.g. Left voicemail. Will try again Friday.",
                            key=f"outreach_notes_{row['lead_id']}"
                        )
                        submit = st.form_submit_button("📞 Log Outreach Outcome", type="primary")
                        if submit:
                            snap_id = snapshot_map.get(row['lead_id'])
                            log_event(row['lead_id'], snap_id, new_status, new_notes, "Internal Wholesaler")
                            st.cache_data.clear()
                            st.rerun()
                elif curr_verif == "Disqualified":
                    st.error("&#x1F6AB; This lead is disqualified. No outreach should be attempted.")
                else:
                    st.markdown(
                        "<div style='background:rgba(255,165,0,0.08); border:1px solid rgba(255,165,0,0.3); "
                        "border-radius:8px; padding:1rem; color:#ccc;'>"
                        "&#x1F512; <strong>Outreach Locked</strong><br>"
                        "Complete Step 1 verification above before logging outreach. "
                        "Verify ownership via Assessor and Recorder links, check lien status, "
                        "then mark as <em>Verified</em> to unlock this section."
                        "</div>",
                        unsafe_allow_html=True
                    )

                # ── Contact Timeline ────────────────────────────────────────
                timeline = load_contact_timeline(row['lead_id'])
                if timeline:
                    with st.expander(f"&#x1F4CB; Contact History ({len(timeline)} event{'s' if len(timeline)!=1 else ''})", expanded=False):
                        kind_icon = {"Verification": "&#x1F50D;", "Outreach": "&#x1F4DE;"}
                        for evt_time, kind, action, notes in timeline:
                            icon = kind_icon.get(kind, "&#x25CF;")
                            import datetime as dt
                            try:
                                utc_dt = dt.datetime.strptime(str(evt_time)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
                                ts = utc_dt.astimezone().strftime("%Y-%m-%d %I:%M %p")
                            except Exception:
                                ts = str(evt_time)[:16]
                            note_str = f" &mdash; <em>{notes}</em>" if notes else ""
                            st.markdown(
                                f"{icon} **{kind}** &bull; `{ts}` &bull; **{action}**{note_str}",
                                unsafe_allow_html=True
                            )


# Export
csv = filtered_df.drop(columns=["Balance_Val", "Opportunity Score", "lead_id"]).to_csv(index=False).encode('utf-8')
st.download_button(
    label="⬇️ Export Filtered Leads to CSV",
    data=csv,
    file_name='distressed_pipeline_export.csv',
    mime='text/csv',
    on_click=lambda: st.toast("CSV Export Triggered Successfully!", icon="✅")
)
