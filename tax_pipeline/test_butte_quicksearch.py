from playwright.sync_api import sync_playwright
import time, json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    
    json_responses = []
    def on_response(resp):
        ct = resp.headers.get('content-type', '')
        if 'json' in ct:
            try:
                json_responses.append({
                    'url': resp.url,
                    'status': resp.status,
                    'body': resp.text()[:5000],
                })
            except:
                pass
    
    page.on("response", on_response)
    
    page.goto("https://common2.mptsweb.com/MBC/butte/tax/search", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)
    
    print("=== Clicking Quick Search dropdown ===")
    quick_search_dd = page.locator("#quickSearch")
    if quick_search_dd.count() > 0:
        quick_search_dd.click()
        time.sleep(1)
    
    # Now the dropdown should be visible
    fee_field = page.locator("input[name='quickSearchFeeParcel']")
    if fee_field.count() > 0:
        fee_field.fill("002271003000", timeout=5000)
        time.sleep(1)
        
        # Look for the search button inside the dropdown
        search_btn = page.locator("#quickSearch button[type='submit'], #quickSearch input[type='submit'], #quickSearch .btn-primary, #quickSearch button:has-text('Search')")
        if search_btn.count() > 0:
            search_btn.first.click()
        else:
            # Just press Enter
            fee_field.press("Enter")
        
        time.sleep(5)
        page.wait_for_load_state("networkidle", timeout=15000)
        
        print(f"Post-search URL: {page.url}")
        
        # Check sessionStorage
        try:
            data = page.evaluate("JSON.parse(sessionStorage.getItem('butte-SearchResults'))")
            if data:
                print(f"\n=== FOUND SEARCH RESULTS ({len(data)} items) ===")
                if isinstance(data, list):
                    for i, item in enumerate(data[:5]):
                        print(f"  [{i}] Owner: {item.get('Owner','?')} | Asmt: {item.get('Asmt','?')} | Situs: {item.get('Situs1','?')}")
            else:
                print("sessionStorage empty")
        except:
            pass
        
        # Check all sessionStorage keys
        try:
            keys = page.evaluate("Object.keys(sessionStorage).join(',')")
            print(f"sessionStorage keys: {keys}")
        except:
            pass
        
        print(f"\nJSON responses: {len(json_responses)}")
        for jr in json_responses:
            print(f"  [{jr['status']}] {jr['url'][:120]}")
    
    browser.close()
