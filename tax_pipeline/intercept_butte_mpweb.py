from playwright.sync_api import sync_playwright
import time, json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    
    # Capture ALL network requests
    api_calls = []
    def on_response(resp):
        url = resp.url
        if any(x in url for x in ['search', 'api', 'json', 'AsrPrint', 'tax']):
            try:
                body = resp.text()
                api_calls.append({
                    'url': url,
                    'status': resp.status,
                    'type': resp.headers.get('content-type', ''),
                    'body_len': len(body),
                    'body': body[:2000],
                })
            except:
                pass
    
    page.on("response", on_response)
    
    # Load the MPTweb tax search page for Butte
    url = 'https://common2.mptsweb.com/MBC/butte/tax/search?f=Q&Asmt=002271003000&TaxYear=2025&RollYear='
    print(f"Loading: {url}")
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(3)
    
    print(f"\n=== Captured {len(api_calls)} API calls ===")
    for api in api_calls:
        print(f"\n  [{api['status']}] {api['url'][:120]}")
        print(f"  Type: {api['type']}")
        print(f"  Body ({api['body_len']} bytes): {api['body'][:500]}")
    
    # Also dump sessionStorage
    try:
        data = page.evaluate("JSON.parse(sessionStorage.getItem('butte-SearchResults'))")
        print(f"\n\n=== sessionStorage butte-SearchResults ===")
        if data:
            print(f"Type: {type(data).__name__}, Length: {len(data) if isinstance(data, (list, dict)) else 'N/A'}")
            if isinstance(data, list):
                print(f"Items: {len(data)}")
                for i, item in enumerate(data[:3]):
                    print(f"  [{i}] {json.dumps(item, default=str)[:300]}")
            elif isinstance(data, dict):
                print(json.dumps(data, default=str)[:500])
        else:
            print("(empty)")
    except Exception as e:
        print(f"sessionStorage error: {e}")
    
    browser.close()
