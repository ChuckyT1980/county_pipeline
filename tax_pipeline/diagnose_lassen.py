from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # visible browser
    page = browser.new_page()

    print("Step 1: Guest login URL")
    page.goto("https://eagleweb.co.lassen.ca.us/eweb/web/loginPOST.jsp?guest=true", timeout=60000)
    page.wait_for_load_state("networkidle", timeout=30000)
    print(f"  URL: {page.url}")
    print(f"  Title: {page.title()}")
    with open("lassen_step1.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    print("  Saved lassen_step1.html")
    time.sleep(2)

    # Look for submit button
    submits = page.locator("input[type='submit']")
    print(f"  Submit buttons found: {submits.count()}")
    if submits.count() > 0:
        for i in range(submits.count()):
            el = submits.nth(i)
            print(f"    [{i}] value={el.get_attribute('value')} id={el.get_attribute('id')} name={el.get_attribute('name')}")
        submits.first.click()
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(2)
        print(f"  After submit URL: {page.url}")
        print(f"  After submit Title: {page.title()}")
        with open("lassen_step2.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print("  Saved lassen_step2.html")

    print("\nStep 3: Look for disclaimer button")
    for sel in ["#submitDisclaimerAccept", "#btnAccept", "#accept", "input[value*='Accept']", "button:has-text('Accept')"]:
        elem = page.locator(sel)
        print(f"  Selector {sel}: count={elem.count()}, visible={elem.first.is_visible() if elem.count() > 0 else False}")

    print("\nStep 4: Look for search field")
    for sel in ["#field_BothNamesID", "input[name*='Name']", "input[id*='Name']", "input[placeholder*='name']"]:
        elem = page.locator(sel)
        print(f"  Selector {sel}: count={elem.count()}, visible={elem.first.is_visible() if elem.count() > 0 else False}")

    print("\nDone. Close the browser window to exit.")
    time.sleep(10)
    browser.close()
