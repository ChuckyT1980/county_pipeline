from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Step 1: Go to ACTIONGROUP first (like Butte) to accept disclaimer
    print("Step 1: Loading dashboard to accept disclaimer...")
    page.goto("https://recorderselfservice.shastacounty.gov/web/action/ACTIONGROUP344S4", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except:
        pass
    time.sleep(3)
    print(f"  URL: {page.url}")

    # Try disclaimer
    accepted = False
    for sel in ["#submitDisclaimerAccept", "button:has-text('Accept')", "input[value*='Accept']"]:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.is_visible():
                loc.click(force=True)
                print(f"  Clicked: {sel}")
                time.sleep(4)
                accepted = True
                break
        except:
            pass

    print(f"  URL after disclaimer: {page.url}")
    print(f"  Accepted: {accepted}")

    # Step 2: Now click the search link from the menu (don't navigate directly)
    print("\nStep 2: Looking for search navigation links...")
    links = page.locator("a[href*='DOCSEARCH'], a[href*='search'], a:has-text('Search')")
    print(f"  Found {links.count()} links")
    for i in range(min(links.count(), 8)):
        href = links.nth(i).get_attribute("href")
        txt = links.nth(i).inner_text()[:50]
        print(f"  [{i}] '{txt}' -> {href}")

    # Try navigating via hash route (SPA style)
    print("\nStep 3: Navigating to search via hash...")
    page.evaluate("window.location.hash = '#/web/search/DOCSEARCH344S4'")
    time.sleep(3)
    print(f"  URL: {page.url}")

    # Check for search field
    for sel in ["#field_BothNamesID", "input[name*='BothNames']", "input[id*='BothNames']", "input[placeholder*='name']"]:
        loc = page.locator(sel)
        if loc.count() > 0:
            print(f"  FOUND search field: {sel}")
            page.fill(sel, "KRIEG")
            time.sleep(1)

            # Click search
            for btn in ["#searchButton", "input[type='submit']", "button[type='submit']"]:
                b = page.locator(btn)
                if b.count() > 0:
                    b.first.click(force=True)
                    print(f"  Clicked search: {btn}")
                    time.sleep(5)
                    break

            # Test selectors
            print("\nResult selectors:")
            for s in [".ui-li-static", "li.ui-li-static", "li[data-role]", "#results_table tbody tr", "table tbody tr", ".search-result"]:
                n = page.locator(s).count()
                status = "OK" if n > 0 else "--"
                print(f"  [{status}] {s}: {n}")
                if n > 0:
                    try:
                        txt = page.locator(s).first.inner_text()[:80].replace('\n',' ')
                        print(f"       -> {txt}")
                    except:
                        pass
            break

    with open("shasta_tyler_results2.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    print("\nSaved: shasta_tyler_results2.html")
    browser.close()
