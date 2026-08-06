from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Go to Shasta Tyler search page
    page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S4", timeout=60000)
    time.sleep(3)

    # Accept disclaimer if present
    try:
        page.click("#submitDisclaimerAccept")
        time.sleep(2)
    except:
        pass

    # Navigate to search page
    page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S4", timeout=60000)
    time.sleep(3)

    # Search for a name that found results (BAILEY)
    page.fill("#field_BothNamesID", "BAILEY BILLY")
    page.click("input[type='submit'][value='Search']", force=True)
    time.sleep(5)

    # Save the HTML
    with open("shasta_tyler_results_user.html", "w", encoding="utf-8") as f:
        f.write(page.content())

    print("Saved. Look for result rows.")

    # Also check what elements are visible
    for sel in [".ui-li-static", ".search-result", ".result-row", "table tbody tr", "li.result", ".ss-result-item"]:
        count = page.locator(sel).count()
        if count > 0:
            print(f"Found {count} rows with selector: {sel}")

    browser.close()
