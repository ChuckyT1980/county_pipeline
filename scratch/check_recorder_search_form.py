"""Check the recorder search form after disclaimer for available search fields"""
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
    
    # Handle any disclaimer
    for attempt in range(5):
        try:
            accept = page.locator("#submitDisclaimerAccept:not([disabled])")
            if accept.count() > 0 and accept.first.is_visible(timeout=2000):
                accept.first.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(1)
                print("[OK] Disclaimer accepted")
                context.storage_state(path=state_file)
            else:
                break
        except:
            time.sleep(1)
    
    # Wait for search form to render
    time.sleep(3)
    
    print("URL:", page.url)
    
    # Get ALL interactive elements
    fields = page.evaluate("""
        () => {
            const els = document.querySelectorAll('input, select, textarea, button, [role="combobox"], [role="listbox"]');
            return Array.from(els).map(el => ({
                tag: el.tagName,
                type: el.type,
                name: el.name,
                id: el.id,
                className: (el.className || '').substring(0, 60),
                placeholder: el.placeholder,
                title: el.title,
                value: el.value,
                text: (el.innerText || '').substring(0, 40),
                visible: el.offsetParent !== null,
                rect: el.getBoundingClientRect ? JSON.stringify(el.getBoundingClientRect()) : ''
            }));
        }
    """)
    
    print("\n=== Interactive elements ===")
    for f in fields:
        if f['id'] or f['name'] or f['text'].strip():
            print("  %-8s id=%-30s name=%-20s placeholder=%-20s text=%s visible=%s" % (
                f['tag'], (f['id'] or '')[:28], (f['name'] or '')[:18], (f['placeholder'] or '')[:18], (f['text'] or '')[:20], f['visible']))
    
    # Try to find a document number search field
    doc_fields = page.evaluate("""
        () => {
            const all = document.querySelectorAll('*');
            return Array.from(all).filter(el => {
                const t = (el.innerText || '').toLowerCase();
                return t.includes('document') || t.includes('doc number') || t.includes('instrument');
            }).map(el => ({
                tag: el.tagName,
                id: el.id,
                text: (el.innerText || '').substring(0, 80),
                type: el.type
            }));
        }
    """)
    
    print("\n=== Document-related elements ===")
    for f in doc_fields:
        print("  %-8s id=%-30s text=%s" % (f['tag'], (f['id'] or '')[:28], (f['text'] or '')[:60]))
    
    # Take a screenshot for debugging
    page.screenshot(path=os.path.join(base_dir, "scratch/recorder_search.png"))
    print("\n[OK] Screenshot saved")
    
    # Save the full HTML
    html = page.content()
    with open(os.path.join(base_dir, "scratch/recorder_search.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("[OK] HTML saved")
    
    browser.close()
