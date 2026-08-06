"""Use Document Number Search (DOCSEARCH344S5) to find owner name"""
from playwright.sync_api import sync_playwright
import time, os, json

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
state_file = os.path.join(base_dir, "tax_pipeline/eagleweb_state.json")
if os.path.exists(state_file):
    os.remove(state_file)

# Doc numbers for our export leads
doc_data = json.load(open(os.path.join(base_dir, 'scratch/shasta_export_doc_numbers.json')))

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
    
    # Go directly to Document Number Search
    page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S5", timeout=60000)
    page.wait_for_load_state("load", timeout=60000)
    time.sleep(3)
    
    print("URL:", page.url)
    
    # Handle disclaimer
    for attempt in range(20):
        try:
            accept = page.locator('#submitDisclaimerAccept')
            if accept.count() > 0 and accept.is_visible(timeout=1000):
                disabled = True
                try:
                    disabled = accept.is_disabled()
                except:
                    pass
                if not disabled:
                    accept.click(timeout=5000)
                    page.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(3)
                    print("Clicked I Accept. URL:", page.url)
                    break
        except:
            pass
        time.sleep(1)
    
    # Extract all form fields
    fields = page.evaluate("""
        () => {
            const inputs = document.querySelectorAll('input:not([type=hidden]), select, textarea, [role=combobox]');
            return Array.from(inputs).map(el => ({
                tag: el.tagName,
                type: el.type,
                id: el.id,
                name: el.name,
                placeholder: el.placeholder,
                title: el.title,
                visible: el.offsetParent !== null,
                label: el.labels && el.labels[0] ? el.labels[0].innerText : '',
                value: el.value || ''
            }));
        }
    """)
    
    print(f"\n=== Form Fields ({len(fields)}) ===")
    for f in fields:
        print(f"  {f['tag']:6s} id={str(f['id'])[:30]:30s} name={str(f['name'])[:25]:25s} placeholder={str(f['placeholder'])[:25]} visible={f['visible']}")
    
    # Also get all text
    text = page.inner_text('body')
    print(f"\n=== Page text ({len(text)} chars) ===")
    # Show first 1500 chars
    print(text[:1500])
    
    # Try the first doc number
    first_apn = list(doc_data.keys())[0]
    doc_num = doc_data[first_apn]
    print(f"\n=== Searching for {first_apn} -> doc {doc_num} ===")
    
    # Convert doc number format: 2017R0021298 -> 2017-0021298
    if 'R' in doc_num:
        doc_num_fmt = doc_num.replace('R', '-')
    else:
        doc_num_fmt = doc_num
    print(f"Formatted doc number: {doc_num_fmt}")
    
    # Enter doc number in the field_DocumentNumberID field
    doc_field = page.locator('#field_DocumentNumberID')
    if doc_field.count() > 0:
        doc_field.fill(doc_num_fmt)
        print(f"Entered: {doc_num_fmt}")
        
        # Find search/submit button
        buttons = page.locator('input[type=submit], button[type=submit], button:has-text("Search")')
        if buttons.count() > 0:
            print("Found submit button")
            buttons.first.click()
        else:
            page.keyboard.press('Enter')
        
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except:
            pass
        time.sleep(5)
        
        print("After search URL:", page.url)
        result = page.inner_text('body')
        print(f"\n=== Results ({len(result)} chars) ===")
        print(result[:3000])
        
        page.screenshot(path=os.path.join(base_dir, "scratch/doc_search_result.png"))
    
    browser.close()
