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
    "shasta": "https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1",
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

def norm(s: str) -> str:
    return " ".join(str(s or "").upper().replace(",", " ").replace(".", " ").split())

def tokens(s: str) -> set:
    return {t for t in norm(s).split() if len(t) > 1}

def owner_tokens(name: str):
    n = norm(name)
    if "," in str(name):
        last, rest = [x.strip() for x in str(name).upper().split(",", 1)]
        first = rest.split()[0] if rest.strip() else ""
        return last, first, tokens(name)
    parts = n.split()
    last = parts[-1] if parts else ""
    first = parts[0] if parts else ""
    return last, first, set(parts)

def strong_name_match(target_name: str, candidate_text: str) -> bool:
    _, _, target_tokens = owner_tokens(target_name)
    cand_tokens = tokens(candidate_text)

    if not target_tokens or not cand_tokens:
        return False

    overlap = target_tokens & cand_tokens
    overlap_ratio = len(overlap) / max(1, len(target_tokens))
    return overlap_ratio >= 0.75

def likely_related_transfer(owner_name: str, grantee_text: str) -> bool:
    _, _, owner_tok = owner_tokens(owner_name)
    grantee_tok = tokens(grantee_text)

    related_markers = {"TRUST", "TRTEE", "TRUSTEE", "REVOCABLE", "FAMILY"}
    return len(owner_tok & grantee_tok) >= 1 and len(related_markers & grantee_tok) >= 1

def ensure_search_ready(page, target_url):
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
                    
            if "DOCSEARCH" not in page.url.upper():
                page.goto(target_url, timeout=30000)
                page.wait_for_load_state("networkidle")
                time.sleep(1)

            field = page.locator("#field_BothNamesID")
            if field.count() > 0 and field.is_visible(timeout=3000):
                return True
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return False

def classify_triage(docs: list, owner_name: str, parcel_level_match: bool = False, recorder_access_blocked: bool = False, detail_snippet: str = "") -> dict:
    """Recorder-gated pessimistic triage classifier for dashboard verification."""

    flags = {
        "ownership_conflict": False,
        "current_owner_candidate": owner_name,
        "active_mortgage": False,
        "estate_flag": False,
        "lien_clear": True,
        "recorder_hit_exists": bool(docs),
        "corroborating_deed": False,
        "parcel_level_match": parcel_level_match,
        "verification_status": "Needs Review",
        "notes": []
    }

    if recorder_access_blocked:
        flags["verification_status"] = "Needs Review"
        flags["notes"].append("Needs Review: Recorder index hit found, but detail view was blocked/failed (recorder_results_but_detail_unconfirmed).")
        flags["notes"] = " ".join(flags["notes"])
        return flags

    if not docs:
        flags["verification_status"] = "Needs Review"
        flags["notes"].append("Needs Review: No recorder corroboration found (no_recorder_results).")
        flags["notes"] = " ".join(flags["notes"])
        return flags

    raw_mortgages = 0
    raw_reconveyances = 0
    latest_conflict_date = ""
    deed_types = {
        "DEED", "GRANT DEED", "QUITCLAIM DEED", "QUIT CLAIM DEED",
        "WARRANTY DEED", "INTERSPOUSAL TRANSFER DEED", "TRUST TRANSFER DEED"
    }

    for d in docs:
        t = norm(d.get("doc_type", ""))
        grantor_text = norm(d.get("grantor", ""))
        grantee_text = norm(d.get("grantee", ""))
        doc_date = str(d.get("recording_date", "") or "")

        if t in {"RECONVEYANCE", "FULL RECONVEYANCE"}:
            raw_reconveyances += 1

        if t in {"DEED OF TRUST", "MORTGAGE"}:
            raw_mortgages += 1

        if t in deed_types:
            if strong_name_match(owner_name, grantee_text):
                flags["corroborating_deed"] = True

            if strong_name_match(owner_name, grantor_text):
                if not strong_name_match(owner_name, grantee_text) and not likely_related_transfer(owner_name, grantee_text):
                    flags["ownership_conflict"] = True
                    if doc_date >= latest_conflict_date:
                        flags["current_owner_candidate"] = d.get("grantee", "") or ""
                        latest_conflict_date = doc_date

        if "ESTATE" in grantor_text or "AFFIDAVIT OF DEATH" in t:
            flags["estate_flag"] = True

        if ("TAX LIEN" in t and "RELEASE" not in t) or t == "ABSTRACT OF JUDGMENT":
            flags["lien_clear"] = False

    flags["active_mortgage"] = max(0, raw_mortgages - raw_reconveyances) > 0

    if flags["ownership_conflict"]:
        flags["verification_status"] = "Disqualified"
        flags["notes"].append(
            f"Disqualified: Ownership conflict in recorder history (possible transfer to {flags['current_owner_candidate']})."
        )
    elif flags["estate_flag"]:
        flags["verification_status"] = "Disqualified"
        flags["notes"].append("Disqualified: Estate/Probate activity detected.")
    elif not flags["corroborating_deed"]:
        flags["verification_status"] = "Needs Review"
        flags["notes"].append("Needs Review: Recorder hit exists but lacks a corroborating deed to the assessor owner.")
    elif not flags["parcel_level_match"]:
        flags["verification_status"] = "Needs Review"
        snippet_text = f" Detail snippet: '{detail_snippet}'" if detail_snippet else ""
        flags["notes"].append(f"Needs Review: Recorder owner match found, but parcel-level linkage is still weak (recorder_results_but_detail_unconfirmed).{snippet_text}")
    elif not flags["lien_clear"]:
        flags["verification_status"] = "Needs Review"
        flags["notes"].append("Needs Review: Active non-mortgage liens found.")
    else:
        flags["verification_status"] = "Verified"
        flags["notes"].append("Verified: Assessor owner aligns with recorder deed and parcel-level linkage is present.")

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
    df['apn_fallback'] = df.get('apn_pdf', df.get('fee_parcel')).fillna(df.get('fee_parcel')).astype(str).str.replace(r"\.0$", "", regex=True)
    def fmt_apn(a):
        digits = re.sub(r"\D", "", a)
        digits = digits.zfill(12)
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9:12]}"
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
            owner_name = str(row.get('assessee_name', row.get('owner_name', '')))
            print(f"Processing {lead_id} ({owner_name})")

            parsed = format_name(owner_name)
            if not parsed:
                log_verification(lead_id, "Needs Review", "Unparseable owner name.")
                continue

            search_str = f"{parsed['lastName']} {parsed['firstName']}".strip()
            docs = []
            
            recorder_access_blocked = False
            detail_snippet = ""
            parcel_level_match = False

            try:
                recorder_url = RECORDER_URLS.get(COUNTY, RECORDER_URLS["tehama"])
                page.goto(recorder_url, timeout=60000)
                if ensure_search_ready(page, recorder_url):
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
                    
                    soup = BeautifulSoup(page.content(), "html.parser")
                    lis = soup.find_all("li", class_="ui-li-static")
                    print(f"    [DEBUG] Found {len(lis)} documents for {search_str}")

                    for li in lis:
                        text = li.text.strip().upper()
                        doc_type_match = re.search(r'TYPE:\s*(.+?)\s*(?:RECORDED:|GRANTOR:|$)', text)
                        dt = doc_type_match.group(1).strip() if doc_type_match else "OTHER"
                        if any(m in text for m in MORTGAGE_TYPES): dt = "MORTGAGE"
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
                        
                        a_tag = li.find("a")
                        href = a_tag.get("href") if a_tag else None
                        
                        docs.append({
                            "doc_type": dt,
                            "grantor": grantor,
                            "grantee": grantee,
                            "recording_date": dm.group(1) if dm else "",
                            "href": href
                        })

            except Exception as e:
                print(f"Error scraping {owner_name}: {e}")
                
            # Stage 2: Click into best candidate deed for parcel matching
            if docs:
                best_deed = None
                deed_types = {"DEED", "GRANT DEED", "QUITCLAIM DEED", "WARRANTY DEED"}
                for d in docs:
                    if d.get("doc_type") in deed_types:
                        if strong_name_match(owner_name, str(d.get("grantee", ""))):
                            best_deed = d
                            break # Take newest strong match

                if best_deed and best_deed.get("href"):
                    detail_url = best_deed["href"]
                    if detail_url.startswith("/"):
                        detail_url = "/".join(recorder_url.split("/")[:3]) + detail_url
                    try:
                        page.goto(detail_url, timeout=30000)
                        time.sleep(2)
                        detail_html = page.content()
                        soup = BeautifulSoup(detail_html, "html.parser")
                        text_content = soup.get_text(separator=' ', strip=True)
                        apn_match = re.search(r'APN[:\s]*([\d\-]+)', text_content, re.IGNORECASE)
                        
                        if apn_match:
                            found_apn = re.sub(r"\D", "", apn_match.group(1))
                            target_apn = re.sub(r"\D", "", str(row['apn_fallback']))
                            
                            if found_apn == target_apn:
                                parcel_level_match = True
                                detail_snippet = text_content[:500]
                                print(f"    [MATCH] APN corroborated exactly: {apn_match.group(1)}")
                            elif found_apn in target_apn or target_apn in found_apn:
                                detail_snippet = f"Substring match only: {found_apn} vs target {target_apn}."
                                print(f"    [MISMATCH] Substring only: Found APN {found_apn} but target is {target_apn}")
                            else:
                                detail_snippet = f"Mismatch: {found_apn} vs target {target_apn}."
                                print(f"    [MISMATCH] Found APN {found_apn} but target is {target_apn}")
                        else:
                            detail_snippet = "No APN pattern found in document text."
                            
                    except Exception as e:
                        recorder_access_blocked = True
                        print(f"    [WARNING] Failed to extract APN detail (access blocked/timed out): {e}")

            flags = classify_triage(docs, owner_name, parcel_level_match=parcel_level_match, recorder_access_blocked=recorder_access_blocked, detail_snippet=detail_snippet)
            log_verification(lead_id, flags["verification_status"], flags["notes"])
            print(f"  -> {flags['verification_status']}: {flags['notes']}")
            
        browser.close()
    print("Done.")

if __name__ == '__main__':
    main()
