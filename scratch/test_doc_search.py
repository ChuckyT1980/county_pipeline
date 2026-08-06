"""Use Document Number Search to find owner name for one lead"""
from playwright.sync_api import sync_playwright
import time, os, json

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
state_file = os.path.join(base_dir, "tax_pipeline/eagleweb_state.json")
if os.path.exists(state_file):
    os.remove(state_file)

# Doc numbers to try
doc_numbers = {
    '070-050-072-000': '2017R0021298',
    '018-600-041-000': '2019R0003944',
}

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
    
    # Go to search URL, handle disclaimer
    page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1", timeout=60000)
    page.wait_for_load_state("load", timeout=60000)
    
    for attempt in range(10):
        try:
            accept = page.locator("#submitDisclaimerAccept")
            if accept.count() > 0 and accept.is_visible(timeout=1000):
                disabled = True
                try:
                    disabled = accept.is_disabled()
                except:
                    pass
                if not disabled:
                    accept.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(2)
                    break
        except:
            pass
        time.sleep(1)
    
    # Navigate to search action group
    page.goto("https://recorderselfservice.shastacounty.gov/web/action/ACTIONGROUP344S2", timeout=60000)
    page.wait_for_load_state("load", timeout=60000)
    time.sleep(2)
    
    # Click "Document Number Search - Web" link
    doc_search_links = page.locator("a:has-text('Document Number Search')")
    if doc_search_links.count() > 0:
        doc_search_links.first.click()
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(3)
        print("Clicked Document Number Search. URL:", page.url)
        
        # Find form fields
        fields = page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('input:not([type=hidden])')).map(el => ({
                    id: el.id,
                    name: el.name,
                    type: el.type,
                    placeholder: el.placeholder,
                    title: el.title,
                    label: el.labels && el.labels[0] ? el.labels[0].innerText : ''
                }));
            }
        """)
        print("\nFields:", json.dumps(fields, indent=2))
        
        # Enter document number for first lead
        doc_num = '2017R0021298'
        
        # Find the input field
        all_inputs = page.locator('input:not([type=hidden])')
        count = all_inputs.count()
        print("\nTotal inputs:", count)
        for i in range(count):
            inp = all_inputs.nth(i)
            pid = inp.get_attribute('id') or ''
            pname = inp.get_attribute('name') or ''
            pph = inp.get_attribute('placeholder') or ''
            ptitle = inp.get_attribute('title') or ''
            print('  [%d] id=%s name=%s placeholder=%s title=%s' % (i, pid, pname, pph, ptitle))
        
        # Try to find document number field
        doc_field = page.locator('#field_NumberID, input[name*="Number"], input[name*="DOCNUM"], input[name*="document"]')
        if doc_field.count() > 0:
            doc_field.first.fill(doc_num)
            print("\nEntered doc number:", doc_num)
            
            # Find and click search/submit button
            search_btn = page.locator('input[type=submit], button:has-text("Search"), input[value*="Search"], input[value*="search"]')
            if search_btn.count() > 0:
                search_btn.first.click()
                page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(3)
                print("\nSearch results URL:", page.url)
                
                # Extract results
                results_text = page.inner_text('body')[:3000]
                print("\nResults:", results_text)
            else:
                print("No search button found")
                # Try pressing Enter
                page.keyboard.press('Enter')
                page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(3)
                print("\nAfter Enter, URL:", page.url)
                print("Results:", page.inner_text('body')[:2000])
        
        # Save screenshot
        page.screenshot(path=os.path.join(base_dir, "scratch/doc_search_results.png"))
    else:
        print("Document Number Search link not found")
        page.screenshot(path=os.path.join(base_dir, "scratch/no_link.png"))
    
    context.storage_state(path=state_file)
    browser.close()
