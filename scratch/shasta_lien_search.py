"""Shasta Lien Search: Name Search on EagleWeb (DOCSEARCH344S4) against 11 owner names"""
from playwright.sync_api import sync_playwright
import time, os, json, re, csv

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
state_file = os.path.join(base_dir, "tax_pipeline", "eagleweb_state.json")

LIEN_TYPES = [
    "FEDERAL TAX LIEN", "STATE TAX LIEN", "ABSTRACT OF JUDGMENT",
    "MECHANIC'S LIEN", "MECHANICS LIEN", "NOTICE OF DELINQUENT ASSESSMENT",
    "NOTICE OF DEFAULT", "LIS PENDENS"
]
SATISFACTION_TYPES = [
    "SATISFACTION OF JUDGMENT", "RELEASE OF LIEN", "RELEASE OF FEDERAL TAX LIEN"
]
MORTGAGE_TYPES = ["DEED OF TRUST", "MORTGAGE"]
RECONVEYANCE_TYPES = ["RECONVEYANCE", "FULL RECONVEYANCE", "SUBSTITUTION OF TRUSTEE AND FULL RECONVEYANCE"]
ASSIGNMENT_TYPES = ["ASSIGNMENT DEED OF TRUST", "ASSIGNMENT OF DEED OF TRUST", "ASSIGNMENT OF RENTS"]
DEED_TYPES = ["GRANT DEED", "QUITCLAIM DEED", "WARRANTY DEED", "CORPORATION GRANT DEED"]

# Load export to get owners and doc numbers
export_path = os.path.join(base_dir, "northern_ca_MASTER_export_with_owners.csv")
leads = []
with open(export_path) as f:
    for row in csv.DictReader(f):
        if row.get("county", "").strip().lower() == "shasta":
            leads.append(row)

print(f"Shasta leads in export: {len(leads)}")
for l in leads:
    print(f"  {l['owner_name'][:38]:38s} {l.get('fee_parcel',''):20s} bal={float(l.get('total_balance',0) or 0):>8.2f}")

# Build owner list (skip SKIP_TRACE_REQUIRED)
owners = []
for l in leads:
    o = l.get("owner_name", "").strip()
    if o and o != "SKIP_TRACE_REQUIRED":
        owners.append({
            "name": o,
            "apn": l.get("fee_parcel", "").strip() or l.get("apn", "").strip(),
            "balance": float(l.get("total_balance", 0) or 0),
            "doc": l.get("recorder_info", "").strip()
        })

print(f"\nOwners to search: {len(owners)}")
for o in owners:
    print(f"  {o['name'][:38]:38s} apn={o['apn']:20s} ${o['balance']:>8.2f}")

def format_name(name):
    name = str(name).strip().upper()
    markers = ["LLC", "INC", "CORP", "CORPORATION", "CO", "COMPANY", "TRUST", "TR", "REVOC",
               "ESTATE", "HOLDINGS", "PROPERTIES", "SERVICES", "ASSOCIATION", "REVOCABLE", "FAMILY"]
    is_entity = any(m in name.split() for m in markers)
    if is_entity:
        return {"lastName": name.replace(",", " ").strip(), "firstName": ""}
    if name.count(",") == 1:
        parts = [p.strip() for p in name.split(",")]
        return {"lastName": parts[0], "firstName": parts[1].split()[0] if parts[1].split() else ""}
    tokens = name.replace(",", " ").split()
    if len(tokens) >= 2:
        return {"lastName": tokens[0], "firstName": tokens[1]}
    return {"lastName": name, "firstName": ""}

def handle_walls(page):
    for _ in range(20):
        try:
            a = page.locator('#submitDisclaimerAccept')
            if a.count() > 0 and a.is_visible(timeout=500):
                if not a.is_disabled():
                    a.click(timeout=3000)
                    time.sleep(2)
                    return
        except: pass
        time.sleep(0.5)

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    
    page.add_init_script("""
        const _orig = window.setTimeout;
        window.setTimeout = function(fn, delay, ...args) {
            if (delay > 1000) delay = 100;
            return _orig(fn, delay, ...args);
        };
    """)
    
    for i, owner in enumerate(owners):
        parsed = format_name(owner["name"])
        search_str = f"{parsed['lastName']} {parsed['firstName']}".strip()
        print(f"\n[{i+1}/{len(owners)}] Searching: '{owner['name']}' -> '{search_str}'")
        
        page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S4", timeout=60000)
        page.wait_for_load_state("load", timeout=60000)
        handle_walls(page)
        
        try:
            name_field = page.locator('#field_BothNamesID')
            if name_field.count() == 0:
                print("  ERROR: Name field not found")
                results.append({"owner": owner, "error": "Field not found", "active_liens": 0, "mortgages": 0, "has_assignment_of_rents": False, "has_affidavit_of_death": False, "ownership_status": "Current"})
                continue
            
            name_field.fill(search_str)
            time.sleep(0.5)
            page.keyboard.press('Enter')
            try: page.wait_for_load_state("networkidle", timeout=15000)
            except: pass
            time.sleep(3)
            
            body = page.inner_text("body")
            
            lines = body.split("\n")
            doc_type = ""
            doc_num = ""
            recording_date = ""
            
            raw_liens = 0
            raw_satisfactions = 0
            raw_mortgages = 0
            raw_reconveyances = 0
            has_assignment = False
            has_affidavit = False
            ownership_status = "Current"
            
            seen_doc_texts = set()
            
            for li in lines:
                text = li.strip().upper()
                if len(text) < 10:
                    continue
                
                # Get doc type
                for dt in DEED_TYPES + MORTGAGE_TYPES + RECONVEYANCE_TYPES + LIEN_TYPES + SATISFACTION_TYPES + ASSIGNMENT_TYPES:
                    if dt in text:
                        doc_type = dt
                        break
                
                # Avoid duplicates
                if text in seen_doc_texts:
                    continue
                seen_doc_texts.add(text)
                
                if any(l in text for l in LIEN_TYPES):
                    raw_liens += 1
                
                if any(s in text for s in SATISFACTION_TYPES):
                    raw_satisfactions += 1
                
                if any(a in text for a in ASSIGNMENT_TYPES):
                    has_assignment = True
                
                if "AFFIDAVIT OF DEATH" in text:
                    has_affidavit = True
                
                if any(m in text for m in MORTGAGE_TYPES):
                    raw_mortgages += 1
                
                if any(r in text for r in RECONVEYANCE_TYPES):
                    raw_reconveyances += 1
            
            active_liens = max(0, raw_liens - raw_satisfactions)
            mortgages = max(0, raw_mortgages - raw_reconveyances)
            
            print(f"  Liens: {active_liens} (raw={raw_liens}, sat={raw_satisfactions})")
            print(f"  Mortgages: {mortgages} (raw={raw_mortgages}, reconv={raw_reconveyances})")
            print(f"  Assignment: {has_assignment}, Affidavit: {has_affidavit}")
            
            results.append({
                "owner": owner,
                "search_term": search_str,
                "active_liens": active_liens,
                "mortgages": mortgages,
                "raw_liens": raw_liens,
                "raw_satisfactions": raw_satisfactions,
                "has_assignment_of_rents": has_assignment,
                "has_affidavit_of_death": has_affidavit,
                "ownership_status": ownership_status
            })
            
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({"owner": owner, "error": str(e), "active_liens": 0})
        
        time.sleep(2)
    
    browser.close()

# Save results
out_path = os.path.join(base_dir, "scratch/shasta_lien_results.json")
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"\n\nResults saved to {out_path}")

# Summary
print("\n=== SHASTA LIEN SEARCH RESULTS ===")
for r in results:
    o = r.get("owner", {})
    liens = r.get("active_liens", r.get("active_liens", 0) if "active_liens" in r else "ERR")
    mrtg = r.get("mortgages", "ERR")
    bal = float(o.get("balance", 0))
    print(f"  {o.get('name','?')[:38]:38s} liens={liens}  mortgages={mrtg}  ${bal:>8.2f}")
