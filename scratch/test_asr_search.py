"""Search Shasta ASR (Assessment Inquiry) for an APN to find owner names"""
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
    
    # Go to ASR site
    page.goto("https://common1.mptsweb.com/mbap/shasta/asr", timeout=60000)
    page.wait_for_load_state("load", timeout=60000)
    time.sleep(3)
    
    print("Page loaded:", page.url)
    
    # Use the main search form
    select = page.locator('#SearchVal')
    if select.count() > 0:
        select.select_option('idfeeparcel')
        print("Selected FEE PARCEL")
    
    input_field = page.locator('#SearchValue')
    if input_field.count() > 0:
        apn = '070-050-072-000'
        input_field.fill(apn)
        print(f"Filled APN: {apn}")
        time.sleep(1)
        
        # Find and click search button
        search_btn = page.locator('input[type=submit][value=Search], button:has-text("Search"), input:has-text("Search")')
        if search_btn.count() > 0:
            search_btn.first.click()
            print("Clicked Search")
        else:
            page.keyboard.press('Enter')
            print("Pressed Enter")
        
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(3)
        
        print("After search URL:", page.url)
        
        # Get page content
        text = page.inner_text('body')
        print(f"\n=== Page Content ({len(text)} chars) ===")
        print(text[:4000])
        
        # Look for owner/name patterns
        print("\n=== Owner/Name Lines ===")
        for line in text.split('\n'):
            ll = line.strip()
            if any(kw in ll.lower() for kw in ['owner', 'name', 'taxpayer', 'mailing', 'lien', 'grantee', 'title', 'situated', 'address']):
                print(f"  {ll[:200]}")
        
        # Look for structured data sections
        print("\n=== All non-empty lines ===")
        for line in text.split('\n'):
            ll = line.strip()
            if ll and len(ll) > 10:
                print(f"  {ll[:200]}")
        
        # Screenshot
        page.screenshot(path=os.path.join(base_dir, "scratch/asr_result.png"))
    
    browser.close()
