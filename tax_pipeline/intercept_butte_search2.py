from playwright.sync_api import sync_playwright
import time, json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    
    # Capture ALL network responses looking for JSON data
    json_responses = []
    def on_response(resp):
        ct = resp.headers.get('content-type', '')
        if 'json' in ct or 'javascript' in ct:
            try:
                body = resp.text()
                json_responses.append({
                    'url': resp.url,
                    'status': resp.status,
                    'type': ct,
                    'body': body[:3000],
                })
            except:
                pass
    
    page.on("response", on_response)
    
    # Load the base search page (no query params = empty form)
    base_url = 'https://common2.mptsweb.com/MBC/butte/tax/search'
    print(f"Loading base search page: {base_url}")
    page.goto(base_url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)
    
    print(f"URL after load: {page.url}")
    print(f"Title: {page.title()}")
    
    # Dump page content to find the search form fields
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page.content(), "html.parser")
    
    # Find search form elements
    print("\n=== Inputs on page ===")
    for inp in soup.find_all("input"):
        name = inp.get("name", "")
        itype = inp.get("type", "")
        placeholder = inp.get("placeholder", "")
        if name and itype != "hidden":
            print(f"  [{itype}] name={name} placeholder={placeholder}")
    
    # Check for the search form
    for form in soup.find_all("form"):
        action = form.get("action", "")
        fid = form.get("id", "")
        print(f"\nForm id={fid} action={action}")
    
    # Look for quickSearchForm
    qs_form = soup.find("form", id="quickSearchForm")
    if qs_form:
        search_url = qs_form.get("data-search-url", "")
        print(f"\nQuickSearch URL: {search_url}")
    
    # Try filling the search field and submitting
    # The base page might have a quick search or main search
    search_fields = page.locator("input[type='search'], input[placeholder*='Search'], input[name='search'], input#quickSearch")
    count = search_fields.count()
    print(f"\nSearch fields found: {count}")
    
    for i in range(count):
        el = search_fields.nth(i)
        fid = el.get_attribute("id")
        fname = el.get_attribute("name")
        print(f"  [{i}] id={fid} name={fname}")
    
    # Try filling the quick search with APN and submitting
    quick_search = page.locator("#quickSearch")
    if quick_search.count() > 0:
        quick_search.fill("002271003000")
        time.sleep(1)
        quick_search.press("Enter")
        time.sleep(5)
        page.wait_for_load_state("networkidle", timeout=15000)
        print(f"\nPost-quick-search URL: {page.url}")
        
        # Check sessionStorage
        try:
            data = page.evaluate("JSON.parse(sessionStorage.getItem('butte-SearchResults'))")
            if data:
                print(f"Found sessionStorage data ({len(data)} items)!")
                if isinstance(data, list):
                    for i, item in enumerate(data[:2]):
                        print(f"  [{i}] Owner={item.get('Owner','?')} Asmt={item.get('Asmt','?')} Situs1={item.get('Situs1','?')}")
            else:
                print("sessionStorage is still empty")
        except Exception as e:
            print(f"sessionStorage error: {e}")
        
        # Print captured JSON responses
        print(f"\nCaptured {len(json_responses)} JSON/JS responses:")
        for jr in json_responses:
            print(f"  [{jr['status']}] {jr['url'][:120]}")
            print(f"  Body: {jr['body'][:300]}")
    
    # Last resort: dump ALL network responses
    print("\n\n=== ALL network responses ===")
    page.goto(base_url + "?f=Q&Asmt=002271003000&TaxYear=2025&RollYear=", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(5)
    
    # Re-check sessionStorage
    try:
        data = page.evaluate("JSON.parse(sessionStorage.getItem('butte-SearchResults'))")
        if data:
            print(f"\nAfter reload: Found sessionStorage data!")
            if isinstance(data, list):
                for i, item in enumerate(data[:2]):
                    print(f"  [{i}] Owner={item.get('Owner','?')} Asmt={item.get('Asmt','?')} Situs1={item.get('Situs1','?')}")
    except:
        print("Still no sessionStorage data")
    
    # List all requests made
    print("\nURLs visited:")
    for resp in page.context.pages[0].expect_response():
        pass  # Too complex, skip
    
    browser.close()
