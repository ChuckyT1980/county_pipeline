"""Check Shasta DOCSEARCH344S4 form fields"""
from playwright.sync_api import sync_playwright
import time, os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    page.add_init_script("""
        const _orig = window.setTimeout;
        window.setTimeout = function(fn, delay, ...args) {
            if (delay > 1000) delay = 100;
            return _orig(fn, delay, ...args);
        };
    """)
    
    page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S4", timeout=60000)
    page.wait_for_load_state("load", timeout=60000)
    
    # Handle disclaimer
    for _ in range(20):
        try:
            a = page.locator('#submitDisclaimerAccept')
            if a.count() > 0 and a.is_visible(timeout=500):
                if not a.is_disabled():
                    a.click(timeout=3000)
                    time.sleep(2)
                    break
        except: pass
        time.sleep(0.5)
    
    print("URL:", page.url)
    
    # Check all input fields
    fields = page.evaluate("""
        () => {
            const inputs = document.querySelectorAll('input, textarea, select');
            return Array.from(inputs).map(el => ({
                id: el.id || '(none)',
                name: el.name || '(none)',
                type: el.type || el.tagName,
                placeholder: el.placeholder || '',
                className: el.className || '',
                visible: el.offsetParent !== null
            }));
        }
    """)
    print("\nForm fields:")
    for f in fields:
        print(f"  id='{f['id']}' name='{f['name']}' type={f['type']} visible={f['visible']}")
    
    # Check all fields starting with field_
    all_ids = page.evaluate("""
        () => {
            return Array.from(document.querySelectorAll('[id]')).map(el => el.id);
        }
    """)
    print("\nAll element IDs:")
    for id_ in sorted(all_ids):
        print(f"  #{id_}")
    
    # Page heading text
    h_text = page.inner_text("h1, h2, h3")
    print(f"\nHeadings: {h_text[:500]}")
    
    # Check if there's a label element
    labels = page.evaluate("""
        () => {
            return Array.from(document.querySelectorAll('label')).map(l => ({
                htmlFor: l.htmlFor,
                text: l.innerText.trim()
            }));
        }
    """)
    print("\nLabels:")
    for l in labels:
        print(f"  for='{l['htmlFor']}' text='{l['text']}'")
    
    browser.close()
