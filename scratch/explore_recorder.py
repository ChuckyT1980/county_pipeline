"""Explore Shasta recorder search options via Playwright"""
from playwright.sync_api import sync_playwright
import time, os, json

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
state_file = os.path.join(base_dir, "tax_pipeline/eagleweb_state.json")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    if os.path.exists(state_file):
        context = browser.new_context(storage_state=state_file)
    else:
        context = browser.new_context()
    
    page = context.new_page()
    
    # Speed up timers
    page.add_init_script("""
        const _orig = window.setTimeout;
        window.setTimeout = function(fn, delay, ...args) {
            if (delay > 1000) delay = 100;
            return _orig(fn, delay, ...args);
        };
    """)
    
    url = "https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1"
    page.goto(url, timeout=60000)
    page.wait_for_load_state("load", timeout=60000)
    
    # Handle disclaimer
    try:
        page.wait_for_selector("#submitDisclaimerAccept:not([disabled])", timeout=20000)
        page.click("#submitDisclaimerAccept")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        context.storage_state(path=state_file)
        print("[OK] Disclaimer accepted")
    except:
        print("[?] No disclaimer or already accepted")
    
    time.sleep(2)
    
    # Print page URL after navigation
    print("Post-disclaimer URL:", page.url)
    
    # Find all input fields, selects, etc.
    fields = page.evaluate("""
        () => {
            const inputs = document.querySelectorAll('input, select, textarea, button');
            const result = [];
            inputs.forEach(el => {
                result.push({
                    tag: el.tagName,
                    type: el.type,
                    name: el.name,
                    id: el.id,
                    placeholder: el.placeholder,
                    label: el.labels ? (el.labels[0] ? el.labels[0].innerText : '') : '',
                    value: el.value,
                    visible: el.offsetParent !== null
                });
            });
            return result;
        }
    """)
    
    print("\n=== Form fields ===")
    for f in fields:
        if f['id'] or f['name']:
            print("  %-10s id=%-30s name=%-20s placeholder=%-20s label=%s" % (
                f['tag'], (f['id'] or '')[:28], (f['name'] or '')[:18], (f['placeholder'] or '')[:18], (f['label'] or '')[:30]))
    
    # Also get the full HTML for the main content
    html = page.content()
    # Save for analysis
    with open(os.path.join(base_dir, "scratch/recorder_page.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("\n[OK] Saved recorder page HTML")
    
    browser.close()
