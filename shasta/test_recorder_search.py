import time
from playwright.sync_api import sync_playwright

def test_doc_search(doc_num):
    print(f"Testing Document Search for {doc_num}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Accepting disclaimer...")
        page.goto("https://recorderselfservice.shastacounty.gov/web/user/disclaimer")
        time.sleep(2)
        page.click("#submitDisclaimerAccept")
        time.sleep(3)
        
        print("Navigating to Document Number Search (S5)...")
        page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S5")
        time.sleep(3)
        
        print(f"Entering Doc Number: {doc_num}")
        page.fill("#field_DocumentNumberID", doc_num)
        page.click("#searchButton")
        
        print("Waiting for results...")
        page.wait_for_selector(".ui-li-static", timeout=15000)
        time.sleep(2)
        
        results = page.query_selector_all(".ui-li-static")
        print(f"Found {len(results)} results.")
        for r in results:
            print(r.inner_text().strip()[:200])
            
        browser.close()

if __name__ == "__main__":
    test_doc_search("2020-0035761")
