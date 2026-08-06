"""Test Name Search on recorder to find liens for a sample owner"""
from playwright.sync_api import sync_playwright
import time, os, json

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
    
    # Go to Name Search
    page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S4", timeout=60000)
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
    
    print(f"Search page URL: {page.url}")
    
    # Get form fields
    fields = page.evaluate("""
        () => {
            return Array.from(document.querySelectorAll('input:not([type=hidden])')).map(el => ({
                id: el.id,
                name: el.name,
                type: el.type,
                placeholder: el.placeholder,
                visible: el.offsetParent !== null
            }));
        }
    """)
    print("\nForm fields:")
    for f in fields:
        print(f"  id={f['id'][:40]:40s} name={f['name'][:40]:40s} visible={f['visible']}")
    
    # Get page text
    text = page.inner_text('body')
    print(f"\nPage text (first 1000):")
    print(text[:1000])
    
    # Try entering a name: GOLDEN YEARS LLC
    # Find the name field
    name_field = page.locator('#field_NameID, input[type=text]')
    if name_field.count() > 0:
        name_field.first.fill('GOLDEN YEARS LLC')
        print("\nEntered: GOLDEN YEARS LLC")
        time.sleep(0.5)
        page.keyboard.press('Enter')
        
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except:
            pass
        time.sleep(5)
        
        print("After search URL:", page.url)
        result = page.inner_text('body')
        print(f"\n=== Results ({len(result)} chars) ===")
        print(result[:2000])
        
        page.screenshot(path=os.path.join(base_dir, "scratch/name_search_result.png"))
    
    browser.close()
