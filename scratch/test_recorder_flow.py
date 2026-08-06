"""Test different EagleWeb navigation flows to find the search form"""
from playwright.sync_api import sync_playwright
import time, os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
state_file = os.path.join(base_dir, "tax_pipeline/eagleweb_state.json")

# Remove old state to start fresh
if os.path.exists(state_file):
    os.remove(state_file)

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
    
    # Flow C: Go to search URL directly, handle disclaimer, then check
    url = "https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1"
    page.goto(url, timeout=60000)
    page.wait_for_load_state("load", timeout=60000)
    print("1. URL:", page.url)
    
    # Try to click I Accept
    for attempt in range(10):
        try:
            accept = page.locator("#submitDisclaimerAccept")
            if accept.count() > 0:
                try:
                    disabled = accept.is_disabled()
                except:
                    disabled = True
                if not disabled and accept.is_visible(timeout=1000):
                    accept.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(2)
                    print("2. Clicked Accept. URL:", page.url)
                    break
        except:
            time.sleep(1)
    
    # Check what's on the page now
    time.sleep(3)
    page_text = page.inner_text('body')[:2000]
    print("3. Page text:", page_text)
    
    # Look for any links that say "Search" or "Records" 
    links = page.evaluate("""
        () => {
            return Array.from(document.querySelectorAll('a')).map(a => ({
                text: (a.innerText || '').trim().substring(0, 60),
                href: a.href || ''
            }));
        }
    """)
    print("\n4. Links on page:")
    for l in links:
        if l['text'] and not l['href'].endswith('#'):
            print('  %-50s -> %s' % (l['text'][:48], l['href'][:80]))
    
    # If redirected to home, find the search link and click it
    for l in links:
        if 'official' in l['text'].lower() or 'records' in l['text'].lower() or 'search' in l['text'].lower():
            if l['href'] and 'DOCSEARCH' in l['href']:
                print("\n5. Found search link, navigating...")
                page.goto(l['href'], timeout=30000)
                time.sleep(3)
                print("6. URL:", page.url)
                page_text2 = page.inner_text('body')[:1000]
                print("7. Page text:", page_text2)
                
                # Check for search fields again
                fields = page.evaluate("""
                    () => {
                        return Array.from(document.querySelectorAll('input, select')).map(el => ({
                            tag: el.tagName,
                            id: el.id,
                            name: el.name,
                            type: el.type
                        })).filter(f => f.id || f.name);
                    }
                """)
                print("\n8. Form fields:", fields)
                break
    
    context.storage_state(path=state_file)
    browser.close()
