from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    # Intercept all XHR/fetch requests to understand the search mechanism
    requests = []
    def on_request(req):
        if 'search' in req.url.lower() or 'POST' in req.method:
            requests.append((req.method, req.url, req.headers))
    page.on("request", on_request)
    
    def handle_disclaimer(url):
        page.goto(url, timeout=60000)
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(2)
        disclaimer = page.locator("#submitDisclaimerAccept")
        if disclaimer.count() > 0 and disclaimer.is_visible(timeout=2000):
            for _ in range(30):
                try:
                    disabled = page.eval_on_selector("#submitDisclaimerAccept", "btn => btn.disabled")
                    if not disabled:
                        disclaimer.click()
                        time.sleep(3)
                        break
                except:
                    pass
                time.sleep(0.5)
    
    # Step 1: Load the Name Search page
    handle_disclaimer("https://recorder.buttecounty.net/web/action/ACTIONGROUP481S1")
    page.goto("https://recorder.buttecounty.net/web/search/DOCSEARCH481S1", timeout=60000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)
    
    # Try entering an APN as a name search (some Tyler systems do this)
    # But first, let's see what POST the Name Search sends
    print("=== Trying to submit Name Search with APN as name ===")
    
    # Try filling the name field with an APN and searching
    name_field = page.locator("#field_BothNamesID")
    if name_field.count() > 0:
        name_field.fill("002271003000", timeout=5000)
        time.sleep(1)
        
        # Click Search
        search_btn = page.locator("#searchButton")
        if search_btn.count() > 0:
            # Clear captured requests
            requests.clear()
            search_btn.click()
            time.sleep(5)
            page.wait_for_load_state("networkidle", timeout=15000)
            
            print(f"\nPost-search URL: {page.url}")
            
            # Check results
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(page.content(), "html.parser")
            
            # Look for results
            results_div = soup.find("div", id=lambda x: x and "search-results" in x)
            if results_div:
                text = results_div.get_text(strip=True)[:500]
                print(f"Results text: {text}")
            
            # Check for list items in results
            for li in soup.find_all("li", class_="ui-li-static"):
                print(f"Result: {li.get_text(strip=True)[:150]}")
    
    browser.close()
