from playwright.sync_api import sync_playwright
import time, json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    
    json_responses = []
    def on_response(resp):
        ct = resp.headers.get('content-type', '')
        if 'json' in ct or 'searchResults' in resp.url:
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
    
    print("=== Setting search type dropdown ===")
    search_type = page.locator("#SearchVal")
    if search_type.count() > 0:
        options = search_type.locator("option").all()
        for opt in options:
            val = opt.get_attribute("value")
            text = opt.inner_text()
            print(f"  option value='{val}' text='{text}'")
        
        # Select APN or Fee Parcel option
        for opt in options:
            text = opt.inner_text().lower()
            if 'apn' in text or 'parcel' in text or 'fee' in text or 'asmt' in text:
                val = opt.get_attribute("value")
                print(f"\nSelecting: {opt.inner_text()} (value={val})")
                search_type.select_option(val)
                break
    
    print("\n=== Filling search value with APN ===")
    search_val = page.locator("#SearchValue")
    search_val.fill("002271003000")
    time.sleep(1)
    
    print("=== Clicking SEARCH ===")
    search_btn = page.locator("#SearchSubmit")
    search_btn.click()
    time.sleep(5)
    page.wait_for_load_state("networkidle", timeout=30000)
    
    print(f"\nPost-search URL: {page.url}")
    
    # Check sessionStorage
    try:
        data = page.evaluate("JSON.parse(sessionStorage.getItem('butte-SearchResults'))")
        if data:
            print(f"\n=== FOUND SEARCH RESULTS ({len(data)} items) ===")
            if isinstance(data, list):
                for i, item in enumerate(data[:5]):
                    print(f"  [{i}] Owner: {item.get('Owner','?')} | Asmt: {item.get('Asmt','?')} | Situs: {item.get('Situs1','?')}")
            elif isinstance(data, dict):
                print(json.dumps(data, default=str)[:500])
        else:
            print("sessionStorage empty")
    except Exception as e:
        print(f"sessionStorage error: {e}")
    
    # Check for other sessionStorage keys with Owner data
    try:
        keys = page.evaluate("Object.keys(sessionStorage).join(',')")
        print(f"\nsessionStorage keys: {keys}")
        for key in keys.split(','):
            if key:
                val = page.evaluate(f"sessionStorage.getItem('{key}')")
                if val and len(val) < 500:
                    print(f"  {key} = {val}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Show relevant page content
    print("\n=== Page content (search results area) ===")
    try:
        # Look for results div
        results = page.locator("#searchResultsDiv, .search-results, .results-area")
        if results.count() > 0:
            print(results.first.inner_text()[:1000])
    except:
        pass
    
    print(f"\nJSON responses: {len(json_responses)}")
    for jr in json_responses:
        print(f"  [{jr['status']}] {jr['url'][:120]}")
    
    # Save the full page HTML
    with open("butte_search_results.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    
    browser.close()
