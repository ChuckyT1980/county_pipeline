"""Batch document number search for all Shasta export leads"""
from playwright.sync_api import sync_playwright
import time, os, json, csv

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
state_file = os.path.join(base_dir, "tax_pipeline/eagleweb_state.json")
if os.path.exists(state_file):
    os.remove(state_file)

# Load doc numbers and export data
doc_data = json.load(open(os.path.join(base_dir, 'scratch/shasta_export_doc_numbers.json')))

# Build fee_parcel -> doc_number mapping (some doc_data keys are fee_parcels)
fee_to_doc = {}
for k, v in doc_data.items():
    fee_to_doc[k] = v  # key could be APN or fee_parcel

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
    
    for apn, doc_raw in list(doc_data.items())[:12]:
        doc_fmt = doc_raw.replace('R', '-')
        print(f"\n{'='*60}")
        print(f"Searching: APN={apn}, Doc={doc_raw} -> {doc_fmt}")
        
        # First search - navigate fresh
        page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S5", timeout=60000)
        page.wait_for_load_state("load", timeout=60000)
        time.sleep(2)
        
        # Handle disclaimer
        for attempt in range(20):
            try:
                accept = page.locator('#submitDisclaimerAccept')
                if accept.count() > 0 and accept.is_visible(timeout=1000):
                    try:
                        disabled = accept.is_disabled()
                    except:
                        disabled = True
                    if not disabled:
                        accept.click(timeout=5000)
                        page.wait_for_load_state("networkidle", timeout=15000)
                        time.sleep(2)
                        break
            except:
                pass
            time.sleep(0.5)
        
        # Enter doc number and search
        doc_field = page.locator('#field_DocumentNumberID')
        if doc_field.count() == 0:
            print("  ERROR: Document number field not found")
            results.append({'apn': apn, 'doc': doc_raw, 'error': 'Field not found', 'grantee': '', 'grantors': []})
            continue
        
        doc_field.fill(doc_fmt)
        time.sleep(0.5)
        page.keyboard.press('Enter')
        
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except:
            pass
        time.sleep(3)
        
        # Extract results
        result_text = page.inner_text('body')
        
        # Parse grantor/grantee
        grantors = []
        grantee = ''
        
        lines = result_text.split('\n')
        in_grantor = False
        in_grantee = False
        for line in lines:
            ll = line.strip()
            if 'Grantor' in ll:
                in_grantor = True
                in_grantee = False
                continue
            if 'Grantee' in ll:
                in_grantor = False
                in_grantee = True
                continue
            if 'Apply Filter' in ll or 'Showing page' in ll or 'Document Number Search' in ll:
                in_grantor = False
                in_grantee = False
                continue
            
            if in_grantor and ll and not ll.startswith('(') and len(ll) > 5:
                grantors.append(ll)
            if in_grantee and ll and not ll.startswith('(') and len(ll) > 5:
                grantee = ll
        
        # Clean grantor names (remove trailing "(1)" etc)
        grantors = [g for g in grantors if not g.startswith('(')]
        # Get first genuine grantor
        grantor = grantors[0] if grantors else ''
        
        print(f"  Grantor: {grantor}")
        print(f"  Grantee: {grantee}")
        
        results.append({
            'apn': apn,
            'doc': doc_raw,
            'doc_fmt': doc_fmt,
            'error': '',
            'grantor': grantor,
            'grantee': grantee,
            'all_grantors': grantors
        })
        
        # Brief delay between searches
        time.sleep(2)
    
    browser.close()

# Save results
output_path = os.path.join(base_dir, 'scratch/shasta_doc_search_results.json')
with open(output_path, 'w') as f:
    json.dump(results, f, indent=2)

print(f"\n\n{'='*60}")
print(f"Results saved to {output_path}")
print(f"Total: {len(results)}")
for r in results:
    grantee = r.get('grantee', '')
    print(f"  {r['apn']} -> Grantee={grantee[:50] if grantee else 'NOT FOUND'}")
