from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    print("Step 1: Load Butte recorder")
    page.goto("https://recorder.buttecounty.net/web/action/ACTIONGROUP201S4", timeout=60000)
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(2)

    disclaimer = page.locator("#submitDisclaimerAccept")
    if disclaimer.count() > 0 and disclaimer.is_visible(timeout=3000):
        print("  Clicking disclaimer...")
        disclaimer.click()
        try:
            page.wait_for_url("**/ACTIONGROUP201S4", timeout=15000)
        except Exception:
            pass
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(2)

    print("\nStep 2: Navigate to ACTUAL Official Records Search")
    # We found DOCSEARCH481S1 via the dashboard HTML!
    page.goto("https://recorder.buttecounty.net/web/search/DOCSEARCH481S1", timeout=60000)
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(3)
    print(f"  Search page URL: {page.url}")
    print(f"  Search page Title: {page.title()}")
    with open("butte_search.html", "w", encoding="utf-8") as f:
        f.write(page.content())

    print("\nStep 3: Try a search")
    name_field = None
    for sel in ["#BothNamesIDSearchString", "#field_BothNamesID", "input[id*='BothNames']", "input[name*='BothNames']", "#field_selfservice_searchName"]:
        if page.locator(sel).count() > 0:
            name_field = sel
            break

    if name_field:
        print(f"  Using name field: {name_field}")
        page.fill(name_field, "SMITH JOHN", timeout=8000)
        time.sleep(1)
        
        search_btns = page.locator("a:has-text('Search'), input[type='submit'][value='Search'], button:has-text('Search')")
        if search_btns.count() > 0:
            search_btns.first.click(force=True)
        else:
            print("  Could not find search button")
            
        time.sleep(5)
        page.wait_for_load_state("networkidle", timeout=30000)
        print(f"  After search URL: {page.url}")
        print(f"  After search Title: {page.title()}")
        with open("butte_results.html", "w", encoding="utf-8") as f:
            f.write(page.content())

        for sel in ["table tbody tr", "ul li", ".ui-li-static", ".ss-listview li", "[data-role='listview'] li"]:
            elems = page.locator(sel)
            print(f"  {sel}: {elems.count()}")
    else:
        print("  Could not find name search field. Let's dump inputs:")
        for sel in ["input[type='text']", "input[name*='Name']", "input[id*='name']", "input[id*='Name']"]:
            elems = page.locator(sel)
            count = elems.count()
            for i in range(min(count, 5)):
                el = elems.nth(i)
                print(f"    [{i}] id={el.get_attribute('id')} name={el.get_attribute('name')} placeholder={el.get_attribute('placeholder')}")


    print("\nDone.")
    time.sleep(5)
    browser.close()
