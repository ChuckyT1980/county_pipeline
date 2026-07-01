import os
import sqlite3
import pandas as pd
import time
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

DB_PATH = "tax_pipeline/cps1_outcomes.db"
CSV_PATH = os.getenv("TRIAGE_CSV", "tax_pipeline/tehama_MASTER_leads_with_liens.csv")
COUNTY   = os.getenv("TRIAGE_COUNTY", "tehama")

RECORDER_URLS = {
    "tehama": "https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1",
    "shasta": "https://eagleweb.co.shasta.ca.us/eaglesoftware/web/search/DOCSEARCH4S1",
}
LEAD_ID_PREFIX = {
    "tehama": "Tehama_",
    "shasta": "Shasta_",
}

# Same imports and lists as cloud_enrichment
LIEN_TYPES = ["FEDERAL TAX LIEN", "STATE TAX LIEN", "ABSTRACT OF JUDGMENT",
              "MECHANIC'S LIEN", "MECHANICS LIEN", "NOTICE OF DELINQUENT ASSESSMENT",
              "NOTICE OF DEFAULT", "LIS PENDENS"]
MORTGAGE_TYPES = ["DEED OF TRUST", "MORTGAGE"]
DEED_TYPES = ["GRANT DEED", "QUITCLAIM DEED", "WARRANTY DEED", "CORPORATION GRANT DEED"]
RECONVEYANCE_TYPES = ["RECONVEYANCE", "FULL RECONVEYANCE",
                       "SUBSTITUTION OF TRUSTEE AND FULL RECONVEYANCE"]
SATISFACTION_TYPES = ["SATISFACTION OF JUDGMENT", "RELEASE OF LIEN",
                       "RELEASE OF FEDERAL TAX LIEN"]

def format_name(name):
    name = str(name).strip().upper()
    if not name or name in {"NAN", "NONE", "UNKNOWN"}:
        return None
    markers = ["LLC", "INC", "CORP", "TRUST", "TR", "REVOC", "ESTATE", "HOLDINGS"]
    if any(m in name.split() for m in markers):
        return {"lastName": name.replace(",", " ").strip(), "firstName": ""}
    if name.count(",") == 1:
        parts = [p.strip() for p in name.split(",")]
        first = parts[1].split()[0] if parts[1].split() else ""
        return {"lastName": parts[0], "firstName": first}
    tokens = name.replace(",", " ").split()
    if len(tokens) >= 2:
        return {"lastName": tokens[0], "firstName": tokens[1]}
    return {"lastName": name, "firstName": ""}

def ensure_search_ready(page):
    for attempt in range(3):
        try:
            if "disclaimer" in page.url.lower():
                try:
                    page.evaluate("""
                        const btn = document.getElementById('submitDisclaimerAccept');
                        if(btn) { btn.disabled = false; btn.click(); }
                    """)
                    page.wait_for_load_state("networkidle")
                    time.sleep(1)
                except Exception:
                    pass
            field = page.locator("#field_BothNamesID")
            if field.count() > 0 and field.is_visible(timeout=3000):
                return True
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return False

def classify_triage(docs: list, owner_name: str) -> dict:
    """Pessimistic triage classifier. Defaults to Needs Review."""
    flags = {
        "ownership_conflict": False,
        "current_owner_candidate": owner_name,
        "active_mortgage": False,
        "estate_flag": False,
        "lien_clear": True,
        "verification_status": "Needs Review", # Fail-safe default
        "notes": []
    }
    
    if not docs:
        flags["notes"].append("No recorder documents found. Manual review required.")
        flags["notes"] = " ".join(flags["notes"])
        return flags
        
    raw_mortgages = 0
    raw_reconveyances = 0
    latest_deed_date = ""

    search_last = owner_name.split(",")[0].strip().upper()
    search_first = owner_name.split(",")[1].strip().upper().split()[0] if "," in owner_name else ""

    for d in docs:
        t = d.get("doc_type", "").upper()
        if t in ["RECONVEYANCE", "FULL RECONVEYANCE"]: raw_reconveyances += 1
        if t in ["DEED OF TRUST", "MORTGAGE"]: raw_mortgages += 1
        if t in ["DEED", "GRANT DEED", "QUITCLAIM DEED", "WARRANTY DEED"]:
            grantor_text = str(d.get("grantor", "")).upper()
            grantee_text = str(d.get("grantee", "")).upper()
            if search_last in grantor_text and (not search_first or search_first in grantor_text):
                is_related = (search_last in grantee_text or any(w in grantee_text for w in ["TRUST", "LLC", "REVOCABLE", "FAMILY"]))
                if not (is_related and search_first and search_first in grantee_text):
                    flags["ownership_conflict"] = True
                    doc_date = d.get("recording_date", "")
                    if doc_date >= latest_deed_date:
                        flags["current_owner_candidate"] = d.get("grantee", "")
                        latest_deed_date = doc_date

        if "ESTATE" in str(d.get("grantor", "")).upper() or "AFFIDAVIT OF DEATH" in t: flags["estate_flag"] = True
        if "TAX LIEN" in t and "RELEASE" not in t: flags["lien_clear"] = False
        if t == "ABSTRACT OF JUDGMENT": flags["lien_clear"] = False

    flags["active_mortgage"] = max(0, raw_mortgages - raw_reconveyances) > 0

    if flags["ownership_conflict"]:
        flags["verification_status"] = "Needs Review"
        flags["notes"].append(f"Ownership Conflict: Transfer detected to {flags['current_owner_candidate']}.")
    elif flags["estate_flag"]:
        flags["verification_status"] = "Needs Review"
        flags["notes"].append("Estate/Probate activity detected.")
    elif not flags["lien_clear"]:
        flags["verification_status"] = "Needs Review"
        flags["notes"].append("Active non-mortgage liens found.")
    else:
        # Only if explicitly clear of all flags AND docs were present
        flags["verification_status"] = "Verified"
        flags["notes"].append("Clean title, no conflicts detected.")

    if flags["active_mortgage"]:
        flags["notes"].append("Active mortgage/DOT exists.")

    flags["notes"] = " ".join(flags["notes"])
    return flags

def log_verification(lead_id, status, notes):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT snapshot_id FROM score_snapshots 
        WHERE lead_id = ? ORDER BY calculated_at DESC LIMIT 1
    ''', (lead_id,))
    snap = cursor.fetchone()
    snap_id = snap[0] if snap else None
    
    cursor.execute('''
        INSERT INTO verification_events (lead_id, snapshot_id, verification_status, wholesaler_name, notes)
        VALUES (?, ?, ?, ?, ?)
    ''', (lead_id, snap_id, status, "System (Triage Engine)", notes))
    conn.commit()
    conn.close()

def get_unverified_leads():
    df = pd.read_csv(CSV_PATH)
    df['apn_fallback'] = df['apn_pdf'].fillna(df['fee_parcel']).astype(str).str.replace(r"\.0$", "", regex=True)
    def fmt_apn(a):
        digits = re.sub(r"\D", "", a)
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9:12]}" if len(digits) == 12 else a
    df['apn_fallback'] = df['apn_fallback'].apply(fmt_apn)
    prefix = LEAD_ID_PREFIX.get(COUNTY, f"{COUNTY.capitalize()}_")
    df['lead_id'] = prefix + df['apn_fallback']

    if not os.path.exists(DB_PATH):
        return df
    
    conn = sqlite3.connect(DB_PATH)
    try:
        verifs = pd.read_sql_query('''
            SELECT lead_id, verification_status 
            FROM verification_events 
            GROUP BY lead_id HAVING event_time = MAX(event_time)
        ''', conn)
        df = df.merge(verifs, on="lead_id", how="left")
        df['verification_status'] = df['verification_status'].fillna('Unverified')
    except Exception:
        df['verification_status'] = 'Unverified'
    finally:
        conn.close()
        
    return df[df['verification_status'].isin(['Unverified', 'Needs Review'])].copy()

def main():
    leads = get_unverified_leads()
    print(f"Found {len(leads)} leads awaiting verification.")
    if leads.empty: return

    limit = int(os.getenv("TRIAGE_LIMIT", len(leads)))
    leads = leads.head(limit)
    print(f"Running triage engine on {len(leads)} leads...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = browser.new_context()
        page = context.new_page()
        page.add_init_script("""
            const _orig = window.setTimeout;
            window.setTimeout = function(fn, delay, ...args) {
                if (delay > 1000) delay = 100;
                return _orig(fn, delay, ...args);
            };
        """)

        for _, row in leads.iterrows():
            lead_id = row['lead_id']
            owner_name = str(row['assessee_name'])
            print(f"Processing {lead_id} ({owner_name})")

            parsed = format_name(owner_name)
            if not parsed:
                log_verification(lead_id, "Needs Review", "Unparseable owner name.")
                continue

            search_str = f"{parsed['lastName']} {parsed['firstName']}".strip()
            docs = []

            try:
                recorder_url = RECORDER_URLS.get(COUNTY, RECORDER_URLS["tehama"])
                page.goto(recorder_url, timeout=60000)
                if ensure_search_ready(page):
                    try:
                        clear_btn = page.locator("#clearSearchButton")
                        if clear_btn.count() > 0 and clear_btn.is_visible(timeout=2000):
                            clear_btn.click()
                            time.sleep(0.5)
                    except Exception:
                        pass

                    page.fill("#field_BothNamesID", search_str, timeout=8000)
                    time.sleep(0.5)
                    page.click("#searchButton")
                    time.sleep(4)
                    
                    try: page.wait_for_selector(".ui-li-static", timeout=8000)
                    except Exception: pass
                    
                    ensure_search_ready(page)
                    soup = BeautifulSoup(page.content(), "html.parser")

                    for li in soup.find_all("li", class_="ui-li-static"):
                        text = li.text.strip().upper()
                        dt = "OTHER"
                        if any(d in text for d in DEED_TYPES): dt = "DEED"
                        elif any(m in text for m in MORTGAGE_TYPES): dt = "MORTGAGE"
                        elif any(r in text for r in RECONVEYANCE_TYPES): dt = "RECONVEYANCE"
                        elif "NOTICE OF POWER TO SELL" in text: dt = "NOTICE OF POWER TO SELL"
                        elif "AFFIDAVIT OF DEATH" in text: dt = "AFFIDAVIT OF DEATH"
                        elif "ASSIGNMENT OF RENTS" in text: dt = "ASSIGNMENT OF RENTS"
                        else:
                            for l in LIEN_TYPES:
                                if l in text: dt = l; break
                            for s in SATISFACTION_TYPES:
                                if s in text: dt = s; break
                                
                        grantor = text.split("GRANTOR:")[1].split("GRANTEE:")[0].strip() if "GRANTOR:" in text else ""
                        grantee = text.split("GRANTEE:")[1].strip() if "GRANTEE:" in text else ""
                        dm = re.search(r'(\d{2}/\d{2}/\d{4})', text)
                        
                        docs.append({
                            "doc_type": dt,
                            "grantor": grantor,
                            "grantee": grantee,
                            "recording_date": dm.group(1) if dm else ""
                        })
            except Exception as e:
                print(f"Error scraping {owner_name}: {e}")
                continue

            flags = classify_triage(docs, owner_name)
            log_verification(lead_id, flags["verification_status"], flags["notes"])
            print(f"  -> {flags['verification_status']}: {flags['notes']}")
            
        browser.close()
    print("Done.")

if __name__ == '__main__':
    main()
