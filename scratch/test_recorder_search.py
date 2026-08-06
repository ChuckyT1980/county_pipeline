"""Navigate to the actual search page and find search form"""
from playwright.sync_api import sync_playwright
import time, os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
state_file = os.path.join(base_dir, "tax_pipeline/eagleweb_state.json")
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
    
    # Go to search URL directly
    url = "https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1"
    page.goto(url, timeout=60000)
    page.wait_for_load_state("load", timeout=60000)
    
    # Handle disclaimer
    for attempt in range(10):
        try:
            accept = page.locator("#submitDisclaimerAccept")
            if accept.count() > 0 and accept.is_visible(timeout=1000):
                try:
                    disabled = accept.is_disabled()
                except:
                    disabled = True
                if not disabled:
                    accept.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(2)
                    print("Clicked Accept")
                    break
        except:
            pass
        time.sleep(1)
    
    # Navigate to the actual search page
    search_url = "https://recorderselfservice.shastacounty.gov/web/action/ACTIONGROUP344S2"
    page.goto(search_url, timeout=60000)
    page.wait_for_load_state("load", timeout=60000)
    time.sleep(3)
    
    print("Search page URL:", page.url)
    
    # Find all form fields
    fields = page.evaluate("""
        () => {
            const inputs = document.querySelectorAll('input:not([type=hidden]), select, textarea, [role=combobox]');
            return Array.from(inputs).map(el => {
                const label = el.labels && el.labels[0] ? el.labels[0].innerText : '';
                const parentText = el.parentElement ? (el.parentElement.innerText || '').trim().substring(0, 50) : '';
                return {
                    tag: el.tagName,
                    type: el.type,
                    id: el.id,
                    name: el.name,
                    title: el.title,
                    placeholder: el.placeholder,
                    label: label,
                    parentText: parentText
                };
            });
        }
    """)
    
    print("\n=== Search Form Fields ===")
    for f in fields:
        print('  id=%-30s name=%-20s label=%s' % (f['id'][:28], f['name'][:18], f['label'][:30] if f['label'] else f['parentText'][:30]))
    
    # Also get all visible text
    text = page.inner_text('body')
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    print('\n=== All visible text (first 80 lines) ===')
    for l in lines[:80]:
        print(l[:200])
    
    context.storage_state(path=state_file)
    browser.close()
