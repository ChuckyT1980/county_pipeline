"""
Stage 2 + 3: Live Verification -> Audit CSV + CRM CSV
Reads a discovery CSV, hits each detail page directly (no JS needed),
extracts live tax data, scores HOT/WARM/COLD/REVIEW.

Install: pip install requests beautifulsoup4 pandas
Run:     python stage2_verify.py tehama tehama_discovery_YYYYMMDD.csv
"""

import re, sys, time, os
from datetime import datetime
import pandas as pd
import requests
from bs4 import BeautifulSoup
try:
    from tax_pipeline.config import COUNTY_CONFIG
except ImportError:
    from config import COUNTY_CONFIG

CHECKPOINT_EVERY = 100

# ── Thresholds
HOT_BALANCE_FLOOR  = 500.0   # balance > $500 AND/OR delinquent = HOT
WARM_BALANCE_FLOOR = 0.01    # any balance > $0 = WARM

DELINQUENT_KEYWORDS = {"DELINQUENT", "UNPAID", "PAST DUE", "DEFAULTED", "LATE"}

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SESSION = requests.Session()
retry_strategy = Retry(
    total=10, 
    backoff_factor=2, 
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
SESSION.mount("https://", adapter)
SESSION.mount("http://", adapter)

SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":     "text/html,application/xhtml+xml",
})


def asmt_nodash(asmt: str) -> str:
    return asmt.replace("-", "")


def parse_dollar(s) -> float:
    if not s:
        return 0.0
    try:
        return float(re.sub(r"[^\d.]", "", str(s)))
    except:
        return 0.0


def fetch_tax_detail(cfg: dict, asmt: str, year: str) -> dict:
    """
    Direct GET to the detail page — confirmed working without JS.
    URL pattern: /MBC/{county}/tax/main/{asmt_no_dashes}/{year}/0000
    """
    url = (f"{cfg['host']}{cfg['appFolder']}{cfg['county_slug']}"
           f"/tax/main/{asmt_nodash(asmt)}/{year}/0000")

    out = {
        "verified_url":      url,
        "verified_at":       datetime.utcnow().isoformat(),
        "v_inst1_status":    None,
        "v_inst1_total_due": None,
        "v_inst1_paid":      None,
        "v_inst1_balance":   None,
        "v_inst2_status":    None,
        "v_inst2_total_due": None,
        "v_inst2_paid":      None,
        "v_inst2_balance":   None,
        "v_total_due":       None,
        "v_total_paid":      None,
        "v_total_balance":   None,
        "v_delinquent":      False,
        "v_fetch_error":     None,
        "assessee_name":     None,
    }

    # ── Pull owner name from MBAP AsrPrint (same source as stage4) ──
    try:
        asr_url = (f"{cfg['host']}/mbap/{cfg['county_slug']}/asr/AsrPrint/"
                   f"{re.sub(r'[^0-9]', '', asmt).zfill(12)}")
        asr_resp = SESSION.get(asr_url, timeout=10)
        if asr_resp.status_code == 200:
            asr_soup = BeautifulSoup(asr_resp.text, "html.parser")
            for tr in asr_soup.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if label in ("Assessee Name", "Owner", "Assessee", "Owner Name") and value:
                        out["assessee_name"] = value
                        break
    except Exception:
        pass  # non-fatal — tax data extraction continues below

    try:
        resp = SESSION.get(url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        lines = [ln.strip() for ln in soup.get_text("\n").split("\n") if ln.strip()]

        def val_after(keyword, search_lines):
            for i, ln in enumerate(search_lines):
                if keyword.lower() in ln.lower():
                    for j in range(i + 1, min(i + 5, len(search_lines))):
                        candidate = search_lines[j]
                        if candidate and candidate.lower() != keyword.lower():
                            return candidate
            return None

        # Find block boundaries
        i1 = next((i for i, l in enumerate(lines) if l.lower() == "installment" and i >= 2 and lines[i-2] == "1" and lines[i-1].lower() == "st"), None)
        i2 = next((i for i, l in enumerate(lines) if l.lower() == "installment" and i >= 2 and lines[i-2] == "2" and lines[i-1].lower() == "nd"), None)
        it = next((i for i, l in enumerate(lines) if "totals" in l.lower()), None)

        if i1 is not None:
            b1 = lines[i1: i2 if i2 else it if it else i1 + 20]
            out["v_inst1_status"]    = val_after("Paid Status", b1)
            out["v_inst1_total_due"] = val_after("Total Due",   b1)
            out["v_inst1_paid"]      = val_after("Total Paid",  b1)
            out["v_inst1_balance"]   = val_after("Balance",     b1)

        if i2 is not None:
            b2 = lines[i2: it if it else i2 + 20]
            out["v_inst2_status"]    = val_after("Paid Status", b2)
            out["v_inst2_total_due"] = val_after("Total Due",   b2)
            out["v_inst2_paid"]      = val_after("Total Paid",  b2)
            out["v_inst2_balance"]   = val_after("Balance",     b2)

        if it is not None:
            bt = lines[it: it + 20]
            out["v_total_due"]     = val_after("Total Due",   bt)
            out["v_total_paid"]    = val_after("Total Paid",  bt)
            out["v_total_balance"] = val_after("Total Balance", bt) or val_after("Balance", bt)

        # Flag delinquency
        for status in [out["v_inst1_status"], out["v_inst2_status"]]:
            if any(kw in str(status).upper() for kw in DELINQUENT_KEYWORDS):
                out["v_delinquent"] = True

    except Exception as e:
        out["v_fetch_error"] = str(e)

    return out


def score(row: dict) -> tuple:
    if row.get("v_fetch_error"):
        return "REVIEW", 0.0

    balance   = parse_dollar(row.get("v_total_balance"))
    delinquent = bool(row.get("v_delinquent"))

    if delinquent and balance >= HOT_BALANCE_FLOOR:
        return "HOT",  0.95
    if delinquent:
        return "HOT",  0.85
    if balance >= HOT_BALANCE_FLOOR:
        return "WARM", 0.80
    if balance >= WARM_BALANCE_FLOOR:
        return "WARM", 0.60
    return "COLD", 0.92


def verify(county: str, discovery_csv: str):
    cfg = COUNTY_CONFIG[county]
    df  = pd.read_csv(discovery_csv, dtype={"asmt": str, "asmt_raw": str, "fee_parcel": str, "apn": str})
    print(f"[Stage 2] Verifying {len(df)} parcels for {county}...")

    # ── Global Support & Resume Support ──
    import sqlite3
    db_path = os.path.join(os.path.dirname(__file__), "cps1_outcomes.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Ensure table exists (safe to run multiple times)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS global_verifications (
            county TEXT,
            asmt TEXT,
            tax_year TEXT,
            verified_score TEXT,
            total_balance REAL,
            PRIMARY KEY (county, asmt, tax_year)
        )
    ''')
    conn.commit()
    tax_year = cfg["tax_year"]
    
    cursor.execute("SELECT asmt FROM global_verifications WHERE county=? AND tax_year=?", (county, tax_year))
    global_verified = set(r[0] for r in cursor.fetchall())

    checkpoint_path = discovery_csv.replace(".csv", "_verify_partial.parquet")
    loaded_asmt = set(global_verified)
    all_rows = []
    if os.path.exists(checkpoint_path):
        existing = pd.read_parquet(checkpoint_path)
        all_rows = existing.to_dict("records")
        for a in existing.get("asmt", []):
            loaded_asmt.add(str(a))
        print(f"[Resume] Loaded {len(existing)} verified parcels from local checkpoint", flush=True)
    else:
        print(f"[Start] No existing checkpoint — verifying from scratch", flush=True)
    print(f"[Global Cache] Found {len(global_verified)} parcels already verified for {county.upper()} ({tax_year}).")

    for i, row in df.iterrows():
        asmt = str(row["asmt"])
        if asmt in loaded_asmt:
            continue  # already verified in a prior run
        year = str(row.get("year", cfg["tax_year"]))
        print(f"  [{i+1}/{len(df)}] {asmt}", end=" ")

        detail          = fetch_tax_detail(cfg, asmt, year)
        tier, conf      = score({**row.to_dict(), **detail})
        detail["verified_score"] = tier
        detail["confidence"]     = conf

        merged = {**row.to_dict(), **detail}
        all_rows.append(merged)
        loaded_asmt.add(asmt)

        status = detail.get("v_total_balance") or detail.get("v_fetch_error") or "?"
        print(f"-> {tier} ({conf:.0%})  balance={status}")
        
        # Save to global cache
        tbal = parse_dollar(detail.get("v_total_balance"))
        cursor.execute('''
            INSERT OR REPLACE INTO global_verifications 
            (county, asmt, tax_year, verified_score, total_balance) 
            VALUES (?, ?, ?, ?, ?)
        ''', (county, asmt, tax_year, tier, tbal))
        conn.commit()
        
        time.sleep(0.05)  # polite delay

        # ── Periodic checkpoint ──
        if len(all_rows) % CHECKPOINT_EVERY == 0:
            pd.DataFrame(all_rows).to_parquet(checkpoint_path, index=False)
            print(f"  [Checkpoint] {len(all_rows)} rows saved", flush=True)

    # Final checkpoint
    pd.DataFrame(all_rows).to_parquet(checkpoint_path, index=False)

    full_df = pd.DataFrame(all_rows)
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Stage 3a: Internal Audit Export (ALL fields, ALL leads)
    audit_path = f"{county}_audit_{ts}.csv"
    full_df.to_csv(audit_path, index=False)
    print(f"\n[OK] Audit export: {audit_path}  ({len(full_df)} rows)")

    # ── Stage 3b: CRM Export (HOT + WARM only, minimal fields)
    crm_cols = [
        "asmt", "fee_parcel", "address", "county", "year",
        "tra", "roll_cat",
        "assessee_name",
        "verified_score", "confidence",
        "v_total_due", "v_total_paid", "v_total_balance",
        "v_inst1_status", "v_inst2_status",
        "v_delinquent",
        "verified_url", "verified_at",
    ]
    crm_df   = full_df[full_df["verified_score"].isin(["HOT", "WARM"])].copy()
    crm_df   = crm_df[[c for c in crm_cols if c in crm_df.columns]]
    crm_df   = crm_df.sort_values("verified_score", ascending=True)  # HOT first
    crm_path = f"{county}_crm_{ts}.csv"
    crm_df.to_csv(crm_path, index=False)

    hot  = len(full_df[full_df["verified_score"] == "HOT"])
    warm = len(full_df[full_df["verified_score"] == "WARM"])
    cold = len(full_df[full_df["verified_score"] == "COLD"])
    rev  = len(full_df[full_df["verified_score"] == "REVIEW"])

    print(f"[OK] CRM export:   {crm_path}  ({len(crm_df)} actionable leads)")
    print(f"\n-- Summary ----------------------")
    print(f"   HOT    : {hot:>5}")
    print(f"   WARM   : {warm:>5}")
    print(f"   COLD   : {cold:>5}")
    print(f"   REVIEW : {rev:>5}")
    print(f"   TOTAL  : {len(full_df):>5}")
    print(f"---------------------------------\n")
    return audit_path, crm_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python stage2_verify.py <county> <discovery_csv>")
        print("Example: python stage2_verify.py tehama tehama_discovery_20260627.csv")
        sys.exit(1)

    county_arg = sys.argv[1]
    csv_arg    = sys.argv[2]
    verify(county_arg, csv_arg)
