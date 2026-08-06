from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    # Guest login
    print("Logging in as guest...")
    page.goto("https://eagleweb.co.lassen.ca.us/eweb/web/loginPOST.jsp?guest=true", timeout=60000)
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(2)
    print(f"After login: {page.url}")

    # Go to search page
    page.goto("https://eagleweb.co.lassen.ca.us/eweb/eagleweb/docSearch.jsp", timeout=60000)
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(2)
    print(f"Search page: {page.url}")
    print(f"Title: {page.title()}")

    # Fill search
    print("Filling search...")
    page.fill("#BothNamesIDSearchString", "SMITH JOHN", timeout=8000)
    time.sleep(1)

    # Click search
    print("Clicking search...")
    page.locator("input[type='submit'][value='Search']").first.click()
    time.sleep(5)
    page.wait_for_load_state("networkidle", timeout=30000)

    print(f"Results URL: {page.url}")
    print(f"Results Title: {page.title()}")

    html = page.content()
    with open("lassen_results.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Saved lassen_results.html")

    # Print a snippet of the body
    body_text = page.inner_text("body")
    print("\n=== BODY TEXT (first 2000 chars) ===")
    print(body_text[:2000])

    time.sleep(5)
    browser.close()
