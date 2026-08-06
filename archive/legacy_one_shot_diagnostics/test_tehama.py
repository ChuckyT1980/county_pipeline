from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    print("Going to Tehama search...")
    page.goto("https://recordsearch.tehama.gov/web/user/disclaimer")
    
    # Accept disclaimer
    try:
        page.evaluate("document.querySelector('#accept').removeAttribute('disabled')")
        page.click("#accept", force=True)
        page.wait_for_url("**/web/search/DOCSEARCH4S2")
        print("Disclaimer accepted.")
    except Exception as e:
        print("Disclaimer issue:", e)
        page.goto("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S2")

    for test_doc in ["2024-001625", "2024001625", "2024-0001625", "24-001625", "20241625"]:
        print(f"Testing doc format: {test_doc}")
        page.goto("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S2")
        page.fill("#field_DocumentNumberID", test_doc)
        page.click("#searchButton")
        try:
            page.wait_for_selector(".results-row, #noDataFragment", timeout=5000)
            if page.query_selector(".results-row"):
                print(f"  -> SUCCESS! Found results for {test_doc}")
                break
            else:
                print(f"  -> No results for {test_doc}")
        except Exception as e:
            print(f"  -> Timeout for {test_doc}")
    browser.close()
