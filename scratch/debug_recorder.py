"""Debug recorder search - find all interactive elements"""
from playwright.sync_api import sync_playwright
import time, os, json

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
    
    # Start at home page and accept disclaimer
    page.goto("https://recorderselfservice.shastacounty.gov/web/", timeout=60000)
    page.wait_for_load_state("load", timeout=60000)
    time.sleep(2)
    print("Home page loaded:", page.url)
    
    # Check for disclaimer
    page_text = page.inner_text('body')
    if 'disclaimer' in page_text.lower() or 'accept' in page_text.lower() or 'i accept' in page_text.lower():
        print("Disclaimer page detected")
        # Try to find accept button
        accept_btn = page.locator('#submitDisclaimerAccept, input[value*="Accept"], button:has-text("Accept")')
        if accept_btn.count() > 0:
            try:
                accept_btn.first.click(timeout=5000)
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(3)
                print("Clicked Accept. URL:", page.url)
            except Exception as e:
                print(f"Click failed: {e}")
    else:
        print("No disclaimer detected")
    
    # Now navigate to the search action group page
    page.goto("https://recorderselfservice.shastacounty.gov/web/action/ACTIONGROUP344S2", timeout=60000)
    page.wait_for_load_state("load", timeout=60000)
    time.sleep(3)
    
    print("\nSearch page loaded:", page.url)
    
    # Get ALL interactive elements
    elements = page.evaluate("""
        () => {
            const allElements = document.querySelectorAll('a, button, input, select, textarea');
            return Array.from(allElements).map(el => ({
                tag: el.tagName,
                id: el.id,
                class: el.className,
                type: el.type,
                name: el.name,
                href: el.href || '',
                text: (el.innerText || el.value || '').trim().substring(0, 80),
                visible: el.offsetParent !== null,
                onclick: el.getAttribute('onclick') || '',
                role: el.getAttribute('role') || ''
            }));
        }
    """)
    
    print(f"\n=== All interactive elements ({len(elements)}) ===")
    for el in elements:
        if el['text'] or el['id']:
            print(f"  {el['tag']:6s} id={el['id'][:30]:30s} text='{el['text'][:60]}' visible={el['visible']} href={el['href'][:60]}")
    
    # Specifically look for document number search
    doc_links = [el for el in elements if 'document' in el['text'].lower() or 'document' in el.get('id','').lower()]
    print(f"\n=== Document-related elements ({len(doc_links)}) ===")
    for el in doc_links:
        print(f"  {el['tag']:6s} id={el['id'][:30]:30s} text='{el['text'][:60]}' href={el['href'][:80]}")
    
    # Save state for next time
    context.storage_state(path=state_file)
    browser.close()
