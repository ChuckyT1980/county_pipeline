from playwright.sync_api import sync_playwright
import time

# Test doc numbers from Butte Stage 1 VERIFIED file
# Format: 2024R0030607 -> trying various formats
test_docs = [
    ("2024-0030607", "year-dash-7digit"),
    ("20240030607",  "all digits no dash"),
    ("2024R0030607", "raw format with R"),
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    print("Navigating to Butte recorder...")
    page.goto("https://recorder.buttecounty.net/web/")
    time.sleep(3)

    # Accept disclaimer if present
    try:
        btn = page.query_selector("button:has-text('I Accept')")
        if btn:
            btn.click()
            time.sleep(2)
            print("Disclaimer accepted.")
    except Exception as e:
        print("No disclaimer or error:", e)

    for doc_fmt, label in test_docs:
        print(f"\nTesting [{label}]: {doc_fmt}")
        try:
            page.goto("https://recorder.buttecounty.net/web/search/DOCSEARCH481S2")
            time.sleep(2)
            page.fill("#field_DocumentNumberID", doc_fmt)
            page.click("#searchButton")
            time.sleep(3)
            rows = page.query_selector_all("li.ss-search-row")
            if rows:
                print(f"  -> SUCCESS! Found {len(rows)} result(s)")
                print(f"  -> Text: {rows[0].inner_text()[:200]}")
                break
            else:
                no_data = page.query_selector("#noDataFragment")
                print(f"  -> No results. No data fragment: {bool(no_data)}")
        except Exception as e:
            print(f"  -> Error: {e}")

    browser.close()
