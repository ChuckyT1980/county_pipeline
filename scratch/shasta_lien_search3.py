"""Shasta Lien Search v3 — fix submit method + only parse doc entries (lines with •)"""
from playwright.sync_api import sync_playwright
import time, os, json, csv

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXPORT_PATH = os.path.join(base_dir, "northern_ca_MASTER_export_with_owners.csv")
RESULT_PATH = os.path.join(base_dir, "scratch/shasta_lien_results.json")

LIEN_TYPES = [
    "TAX LIEN", "FEDERAL TAX LIEN", "STATE TAX LIEN", "ABSTRACT OF JUDGMENT",
    "MECHANIC'S LIEN", "MECHANICS LIEN", "NOTICE OF DELINQUENT ASSESSMENT",
    "NOTICE OF DEFAULT", "LIS PENDENS", "LIEN"
]
SATISFACTION_TYPES = [
    "SATISFACTION OF JUDGMENT", "RELEASE OF LIEN", "RELEASE OF FEDERAL TAX LIEN",
    "RELEASE OF ASSESSMENT LIEN"
]
MORTGAGE_TYPES = ["DEED OF TRUST", "MORTGAGE"]
RECONVEYANCE_TYPES = ["RECONVEYANCE", "FULL RECONVEYANCE", "SUBSTITUTION OF TRUSTEE AND FULL RECONVEYANCE"]
ASSIGNMENT_TYPES = ["ASSIGNMENT DEED OF TRUST", "ASSIGNMENT OF DEED OF TRUST", "ASSIGNMENT OF RENTS"]

owners = []
with open(EXPORT_PATH) as f:
    for row in csv.DictReader(f):
        if row.get("county", "").strip().lower() == "shasta":
            o = row.get("owner_name", "").strip()
            if o and o != "SKIP_TRACE_REQUIRED":
                owners.append({
                    "name": o,
                    "apn": row.get("fee_parcel", "").strip() or row.get("apn", "").strip(),
                    "balance": float(row.get("total_balance", 0) or 0),
                    "doc": row.get("recorder_info", "").strip()
                })

print(f"Owners to search: {len(owners)}")
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
        print(f"\n[{i+1}/{len(owners)}] {owner['name']} -> '{search_str}'")
        
        page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S4", timeout=60000)
        page.wait_for_load_state("load", timeout=60000)
        
        # Handle walls
        for _ in range(30):
            if "disclaimer" in page.url.lower():
                try:
                    a = page.locator('#submitDisclaimerAccept')
                    if a.count() > 0 and a.is_visible(timeout=500):
                        if not a.is_disabled():
                            a.click(timeout=3000)
                            time.sleep(1)
                except: pass
            else:
                break
            time.sleep(1)
        
        try:
            page.locator('#field_BothNamesID').fill(search_str)
            time.sleep(0.5)
            page.locator('#searchButton').click()
            
            try: page.wait_for_load_state("networkidle", timeout=15000)
            except: pass
            time.sleep(4)
            
            body = page.inner_text("body")
            
            # Parse — only lines after "Showing page" to avoid filter summary
            parts = body.split("Showing page")
            doc_section = parts[1] if len(parts) > 1 else body
            
            lines = doc_section.upper().split("\n")
            
            raw_liens = 0
            raw_satisfactions = 0
            raw_mortgages = 0
            raw_reconveyances = 0
            has_assignment = False
            has_affidavit = False
            doc_records = []
            
            seen = set()
            for line in lines:
                text = line.strip()
                if "•" not in text:
                    continue
                if text in seen:
                    continue
                seen.add(text)
                doc_records.append(text)
                
                ut = text.upper()
                ut = text.upper()
                is_lien = any(l in ut for l in LIEN_TYPES)
                is_release = "RELEASE" in ut or "SATISFACTION" in ut
                if is_lien and not is_release:
                    raw_liens += 1
                if is_release:
                    raw_satisfactions += 1
                if any(m in ut for m in MORTGAGE_TYPES):
                    raw_mortgages += 1
                if any(r in ut for r in RECONVEYANCE_TYPES):
                    raw_reconveyances += 1
                if any(a in ut for a in ASSIGNMENT_TYPES):
                    has_assignment = True
                if "AFFIDAVIT OF DEATH" in ut:
                    has_affidavit = True
            
            active_liens = max(0, raw_liens - raw_satisfactions)
            mortgages_net = max(0, raw_mortgages - raw_reconveyances)
            
            print(f"  docs={len(doc_records)} liens={active_liens} (raw={raw_liens}, sat={raw_satisfactions}) mortgages={mortgages_net} (raw={raw_mortgages}, rec={raw_reconveyances})")
            for d in doc_records[:5]:
                print(f"    {d[:80]}")
            if len(doc_records) > 5:
                print(f"    ... ({len(doc_records)} total)")
            
            results.append({
                "owner": owner,
                "search_term": search_str,
                "active_liens": active_liens,
                "mortgages_net": mortgages_net,
                "raw_liens": raw_liens,
                "raw_satisfactions": raw_satisfactions,
                "raw_mortgages": raw_mortgages,
                "raw_reconveyances": raw_reconveyances,
                "has_assignment_of_rents": has_assignment,
                "has_affidavit_of_death": has_affidavit,
                "ownership_status": "Current",
                "total_records_found": len(doc_records),
                "doc_records": doc_records
            })
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({"owner": owner, "error": str(e)})
        
        time.sleep(2)
    
    browser.close()

with open(RESULT_PATH, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nSaved to {RESULT_PATH}")

print(f"\n{'='*60}")
print("FINAL RESULTS:")
for r in results:
    o = r.get("owner", {})
    liens = r.get("active_liens", "?")
    mrtg = r.get("mortgages_net", "?")
    bal = float(o.get("balance", 0))
    name = o.get("name", "?").strip()
    found = r.get("total_records_found", 0)
    print(f"  {name[:38]:38s} liens={liens}  mortgages={mrtg}  docs={found}  ${bal:>8.2f}")
