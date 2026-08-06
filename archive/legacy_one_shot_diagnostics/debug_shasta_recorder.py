import time
from playwright.sync_api import sync_playwright

def run_debug():
    print("Starting Shasta Recorder Debug...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # 1. Go to search page
        login_url = "https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1"
        print(f"Navigating to {login_url}")
        page.goto(login_url, timeout=60000)
        page.wait_for_load_state("networkidle")
        
        # 2. Handle disclaimer if present
        try:
            if page.locator("#submitDisclaimerAccept").is_visible(timeout=5000):
                print("Clicking disclaimer...")
                page.locator("#submitDisclaimerAccept").click()
                page.wait_for_load_state("networkidle")
        except Exception as e:
            print(f"No disclaimer found or error: {e}")
            
        time.sleep(2)
        
        # 3. Enter search name
        # Using a name from our shasta leads: "TRUENORTH INC" or "SANCHEZ, RAMIRO"
        test_name = "SANCHEZ, RAMIRO"
        print(f"Searching for: {test_name}")
        
        search_field = page.locator("#field_BothNamesID")
        search_field.fill(test_name)
        
        # 4. Click search
        print("Clicking search...")
        try:
            page.locator("#searchButton").click(force=True)
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception as e:
            print("Timeout waiting for search results")
            
        time.sleep(5) # Give it extra time to load results
        
        html = page.content()
        with open("shasta_debug_results.html", "w", encoding="utf-8") as f:
            f.write(html)
            
        print("Saved shasta_debug_results.html")
        
        # Try to find result selectors
        import re
        results = page.locator(".ui-li-static")
        print(f"Found {results.count()} results with .ui-li-static")
        
        results2 = page.locator(".result-item")
        print(f"Found {results2.count()} results with .result-item")
        
        results3 = page.locator("li.ui-li")
        print(f"Found {results3.count()} results with li.ui-li")
        
        browser.close()

if __name__ == "__main__":
    run_debug()
