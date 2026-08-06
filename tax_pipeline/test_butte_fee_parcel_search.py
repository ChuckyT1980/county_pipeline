from playwright.sync_api import sync_playwright
import time, json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    
    # Capture JSON responses
    json_responses = []
    def on_response(resp):
        ct = resp.headers.get('content-type', '')
        if 'json' in ct:
            try:
                body = resp.text()
                json_responses.append({
                    'url': resp.url,
                    'status': resp.status,
                    'body': body[:5000],
                })
            except:
                pass
    
    page.on("response", on_response)
    
    # Load the search page
    page.goto("https://common2.mptsweb.com/MBC/butte/tax/search", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)
    
    print("=== Filling quickSearchFeeParcel ===")
    fee_field = page.locator("input[name='quickSearchFeeParcel']")
    if fee_field.count() > 0:
        fee_field.fill("002271003000", timeout=5000)
        time.sleep(1)
        
        # Try pressing Enter
        fee_field.press("Enter")
        time.sleep(5)
        page.wait_for_load_state("networkidle", timeout=15000)
        
        print(f"Post-search URL: {page.url}")
        
        # Check sessionStorage for search results
        try:
            data = page.evaluate("JSON.parse(sessionStorage.getItem('butte-SearchResults'))")
            if data:
                print(f"\n=== FOUND SEARCH RESULTS ({len(data)} items) ===")
                if isinstance(data, list):
                    for i, item in enumerate(data[:5]):
                        owner = item.get('Owner', '?')
                        asmt = item.get('Asmt', '?')
                        situs = item.get('Situs1', '?')
                        tra = item.get('TRA', '?')
                        ty = item.get('Taxyear', '?')
                        print(f"  [{i}] Owner: {owner} | Asmt: {asmt} | Situs: {situs} | TRA: {tra} | Year: {ty}")
            else:
                print("sessionStorage empty")
        except Exception as e:
            print(f"sessionStorage error: {e}")
        
        # Also check for other sessionStorage keys
        try:
            all_keys = page.evaluate("[window.location.href, Object.keys(sessionStorage).join(',')]")
            print(f"\nURL: {all_keys[0]}")
            print(f"sessionStorage keys: {all_keys[1]}")
        except Exception as e:
            print(f"Error: {e}")
        
        # Print JSON responses
        print(f"\n=== JSON responses ({len(json_responses)}) ===")
        for jr in json_responses:
            print(f"  [{jr['status']}] {jr['url'][:120]}")
            print(f"  Body: {jr['body'][:500]}")
    
    browser.close()
