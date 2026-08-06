"""Batch document number search - proper HTML-based extraction"""
from playwright.sync_api import sync_playwright
import time, os, json, csv

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
state_file = os.path.join(base_dir, "tax_pipeline/eagleweb_state.json")
if os.path.exists(state_file):
    os.remove(state_file)

# Load doc numbers
doc_data = json.load(open(os.path.join(base_dir, 'scratch/shasta_export_doc_numbers.json')))

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
    
    for apn, doc_raw in doc_data.items():
        doc_fmt = doc_raw.replace('R', '-')
        print(f"\n{'='*60}")
        print(f"Searching: APN={apn}, Doc={doc_fmt}")
        
        page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S5", timeout=60000)
        page.wait_for_load_state("load", timeout=60000)
        time.sleep(1)
        
        # Handle disclaimer
        for _ in range(20):
            try:
                a = page.locator('#submitDisclaimerAccept')
                if a.count() > 0 and a.is_visible(timeout=500):
                    if not a.is_disabled():
                        a.click(timeout=3000)
                        time.sleep(2)
                        break
            except:
                pass
            time.sleep(0.5)
        
        # Enter doc number and search
        page.locator('#field_DocumentNumberID').fill(doc_fmt)
        time.sleep(0.5)
        page.keyboard.press('Enter')
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except:
            pass
        time.sleep(3)
        
        # Extract grantor/grantee from the filter section
        grantee = ""
        grantors = []
        doc_type = ""
        recording_date = ""
        
        # Method 1: Extract from filter section
        filter_data = page.evaluate("""
            () => {
                const filters = document.getElementById('filters');
                if (!filters) return null;
                
                const result = {};
                
                // Get all h2 elements inside filters
                const h2s = filters.querySelectorAll('h2');
                h2s.forEach(h2 => {
                    const header = h2.innerText.trim();
                    // Next sibling ul contains the items
                    let ul = h2.nextElementSibling;
                    if (ul && ul.tagName === 'UL') {
                        const items = Array.from(ul.querySelectorAll('li')).map(li => li.innerText.trim());
                        result[header] = items;
                    }
                });
                
                // Also get description
                const descDiv = filters.querySelector('.ss-description');
                if (descDiv) {
                    result['description'] = descDiv.innerText.trim();
                }
                
                return result;
            }
        """)
        
        if filter_data:
            for key, items in filter_data.items():
                if 'grantor' in key.lower():
                    grantors = items
                elif 'grantee' in key.lower():
                    grantee = items[0] if items else ""
                elif 'description' in key.lower():
                    doc_type = items
                else:
                    print(f"    Other: {key}: {items}")
        
        # Method 2: Also try from result rows
        if not grantee:
            result_data = page.evaluate("""
                () => {
                    const result = {};
                    // Look for the search result list
                    const lists = document.querySelectorAll('ul.selfServiceSearchResultList');
                    lists.forEach(ul => {
                        const items = ul.querySelectorAll('li');
                        items.forEach(li => {
                            const text = li.innerText.trim();
                            // Find grantor/grantee sections
                            const grantorMatch = text.match(/Grantor\s*\(\d+\)\s*([\\s\\S]*?)(?:Grantee|$)/);
                            const granteeMatch = text.match(/Grantee[\\s\\S]*?(\\n[^\\n]+)/);
                            if (grantorMatch) {
                                if (!result.grantors) result.grantors = [];
                                const names = grantorMatch[1].trim().split('\\n').map(s => s.trim()).filter(s => s);
                                result.grantors.push(...names);
                            }
                            if (granteeMatch) {
                                result.grantee = granteeMatch[1].trim();
                            }
                        });
                    });
                    return result;
                }
            """)
            
            if result_data:
                if result_data.get('grantee') and not grantee:
                    grantee = result_data['grantee']
        
        print(f"  DocType={doc_type}")
        print(f"  Grantors ({len(grantors)}): {grantors}")
        print(f"  Grantee: {grantee}")
        
        results.append({
            'apn': apn,
            'doc': doc_raw,
            'doc_fmt': doc_fmt,
            'doc_type': doc_type,
            'grantors': grantors,
            'grantee': grantee
        })
        
        time.sleep(2)
    
    browser.close()

# Save
output_path = os.path.join(base_dir, 'scratch/shasta_doc_search_results.json')
with open(output_path, 'w') as f:
    json.dump(results, f, indent=2)

print(f"\n\n{'='*60}")
print("FINAL RESULTS:")
for r in results:
    print(f"  {r['apn']}: Grantee={r['grantee'][:50] if r['grantee'] else 'NOT FOUND'}")
