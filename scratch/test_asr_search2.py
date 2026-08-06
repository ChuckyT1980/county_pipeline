"""Search Shasta ASR - handle cookies, use main search form"""
from playwright.sync_api import sync_playwright
import time, os

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
    
    page.goto("https://common1.mptsweb.com/mbap/shasta/asr", timeout=60000)
    page.wait_for_load_state("load", timeout=60000)
    time.sleep(3)
    
    # Accept cookies
    try:
        cookie_btn = page.locator('button:has-text("Accept"), a:has-text("Accept")')
        if cookie_btn.count() > 0 and cookie_btn.first.is_visible(timeout=2000):
            cookie_btn.first.click()
            print("Accepted cookies")
            time.sleep(2)
    except:
        print("No cookie button")
    
    # Set search type to FEE PARCEL
    page.locator('#SearchVal').select_option('idfeeparcel')
    print("Selected FEE PARCEL")
    
    # Enter APN
    page.locator('#SearchValue').fill('070-050-072-000')
    print("Entered APN")
    
    # Press Enter to submit
    page.keyboard.press('Enter')
    print("Pressed Enter")
    
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(5)
    
    print("After submit URL:", page.url)
    text = page.inner_text('body')
    print(f"Content ({len(text)} chars):")
    print(text[:5000])
    
    # Look for owner/name lines
    print("\n=== Owner/Name/Property Lines ===")
    for line in text.split('\n'):
        ll = line.strip()
        if any(kw in ll.lower() for kw in ['owner', 'name', 'taxpayer', 'mailing', 'lien', 'grantee', 'title', 'situated', 'address', 'parcel', 'property']):
            if len(ll) > 5:
                print(f"  {ll[:200]}")
    
    # Screenshot
    page.screenshot(path=os.path.join(base_dir, "scratch/asr_result2.png"))
    
    browser.close()
