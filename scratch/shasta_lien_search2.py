"""Shasta Lien Search v2 - with debugging and page checking"""
from playwright.sync_api import sync_playwright
import time, os, json, re, csv

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

owners = [
    {"name": "GOLDEN YEARS LLC", "apn": "070-050-072-000", "balance": 26469.92, "doc": ""},
    {"name": "TRUENORTH INC", "apn": "064-100-031-000", "balance": 21962.11, "doc": ""},
    {"name": "SANCHEZ, RAMIRO", "apn": "018-600-041-000", "balance": 16000.82, "doc": ""},
    {"name": "CLEARWATER REAL ESTATE HOLDINGS LLC", "apn": "097-150-016-000", "balance": 10778.98, "doc": ""},
    {"name": "JONES, HAROLD L - TR", "apn": "085-050-022-000", "balance": 9015.84, "doc": ""},
    {"name": "MULLINS, DAVID F", "apn": "102-450-028-000", "balance": 8136.06, "doc": ""},
]

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
        print(f"\n[{i+1}/{len(owners)}] {owner['name']} -> search='{search_str}'")
        
        page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S4", timeout=60000)
        page.wait_for_load_state("load", timeout=60000)
        print(f"  URL: {page.url}")
        
        # Handle walls
        for attempt in range(30):
            url = page.url
            if "disclaimer" in url.lower():
                try:
                    a = page.locator('#submitDisclaimerAccept')
                    if a.count() > 0 and a.is_visible(timeout=500):
                        if not a.is_disabled():
                            a.click(timeout=3000)
                            time.sleep(2)
                            print(f"  Clicked disclaimer (attempt {attempt+1})")
                except: pass
            else:
                break
            time.sleep(1)
        
        print(f"  After wall handling URL: {page.url}")
        
        # Check for session keepalive
        try:
            keepalive = page.locator("button:has-text('Yes - Continue'), button:has-text('Yes, Continue')")
            if keepalive.count() > 0 and keepalive.first.is_visible(timeout=1000):
                keepalive.first.click()
                time.sleep(1)
                print("  Handled keepalive")
        except: pass
        
        try:
            # Check if field exists
            field_exists = page.evaluate("!!document.getElementById('field_BothNamesID')")
            if not field_exists:
                print("  ERROR: field_BothNamesID not found")
                # Debug: dump first part of body
                body_preview = page.inner_text("body")[:1000]
                print(f"  Body preview: {body_preview[:500]}")
                results.append({"owner": owner, "error": "Field not found"})
                continue
            
            name_field = page.locator('#field_BothNamesID')
            print(f"  Field exists, filling: '{search_str}'")
            
            name_field.fill(search_str)
            time.sleep(0.5)
            page.locator('#searchButton').click()
            
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass
            time.sleep(4)
            
            print(f"  After search URL: {page.url}")
            body = page.inner_text("body")
            print(f"  Results length: {len(body)} chars")
            
            # Check for no results
            if "No Results" in body or "no results" in body.lower():
                print(f"  NO RESULTS for '{search_str}'")
                results.append({"owner": owner, "active_liens": 0, "mortgages": 0, "mortgages_net": 0, "has_assignment_of_rents": False, "has_affidavit_of_death": False, "ownership_status": "Current"})
                continue
            
            lines = body.upper().split("\n")
            
            raw_liens = 0
            raw_satisfactions = 0
            raw_mortgages = 0
            raw_reconveyances = 0
            has_assignment = False
            has_affidavit = False
            ownership_status = "Current"
            
            seen = set()
            for line in lines:
                text = line.strip()
                if len(text) < 10 or text in seen:
                    continue
                seen.add(text)
                
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
            mortgages_net = max(0, raw_mortgages - raw_reconveyances)
            
            print(f"  liens={active_liens} (raw={raw_liens}, sat={raw_satisfactions})  mortgages={mortgages_net} (raw={raw_mortgages}, rec={raw_reconveyances})")
            print(f"  assignment={has_assignment}  affidavit={has_affidavit}")
            
            results.append({
                "owner": owner,
                "search_term": search_str,
                "active_liens": active_liens,
                "mortgages": raw_mortgages,
                "mortgages_net": mortgages_net,
                "raw_liens": raw_liens,
                "raw_satisfactions": raw_satisfactions,
                "raw_reconveyances": raw_reconveyances,
                "has_assignment_of_rents": has_assignment,
                "has_affidavit_of_death": has_affidavit,
                "ownership_status": ownership_status
            })
            
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            try:
                page.screenshot(path=os.path.join(base_dir, "scratch/shasta_lien_error.png"))
            except: pass
            results.append({"owner": owner, "error": str(e)})
        
        time.sleep(2)
    
    browser.close()

out_path = os.path.join(base_dir, "scratch/shasta_lien_results.json")
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nSaved to {out_path}")

print(f"\n{'='*60}")
print("RESULTS:")
for r in results:
    o = r.get("owner", {})
    liens = r.get("active_liens", "?")
    mrtg = r.get("mortgages_net", r.get("mortgages", "?"))
    bal = float(o.get("balance", 0))
    name = o.get("name", "?").strip()
    print(f"  {name[:38]:38s} liens={liens}  mortgages={mrtg}  ${bal:>8.2f}")
