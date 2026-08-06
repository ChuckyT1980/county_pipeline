"""Debug what Shasta search returns"""
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
    
    # Handle walls
    for _ in range(30):
        if "disclaimer" in page.url.lower():
            try:
                a = page.locator('#submitDisclaimerAccept')
                if a.count() > 0 and a.is_visible(timeout=500):
                    if not a.is_disabled():
                        a.click(timeout=3000)
                        time.sleep(1)
            except: pass
        else:
            break
        time.sleep(1)
    
    print(f"Search page ready. URL: {page.url}")
    
    # Enter name
    page.locator('#field_BothNamesID').fill("GOLDEN YEARS LLC")
    time.sleep(0.5)
    
    # Click search button
    page.locator('#searchButton').click()
    time.sleep(5)
    
    try: page.wait_for_load_state("networkidle", timeout=15000)
    except: pass
    time.sleep(3)
    
    print(f"After search URL: {page.url}")
    
    # Dump ALL text
    body_full = page.inner_text("body")
    print(f"\n=== FULL BODY ({len(body_full)} chars) ===")
    print(body_full)
    
    # Also dump HTML structure
    html_struct = page.evaluate("""
        () => {
            const body = document.body;
            function walk(el, depth) {
                let result = '';
                const tag = el.tagName ? el.tagName.toLowerCase() : '#text';
                const cls = el.className ? '.' + el.className.split(' ').join('.') : '';
                const id = el.id ? '#' + el.id : '';
                const visible = el.offsetParent !== null;
                if (tag === '#text') return '';
                if (['script','style','meta','link'].includes(tag)) return '';
                const text = (el.innerText || '').trim().substring(0, 60);
                if (depth < 4) {
                    result += '  '.repeat(depth) + tag + id + cls + ' [' + text + '] visible=' + visible + '\\n';
                    for (let child of el.children) {
                        result += walk(child, depth + 1);
                    }
                }
                return result;
            }
            return walk(body, 0);
        }
    """)
    print(f"\n=== HTML STRUCTURE ===")
    print(html_struct)
    
    # Check results
    results_area = page.evaluate("""
        () => {
            const el = document.getElementById('SelfService-1782998281662-search-results');
            return el ? el.innerText : 'NOT FOUND';
        }
    """)
    print(f"\n=== search-results area ===")
    print(results_area)
    
    page.screenshot(path=os.path.join(base_dir, "scratch/shasta_search_debug.png"))
    print("\nScreenshot saved to scratch/shasta_search_debug.png")
    
    browser.close()
