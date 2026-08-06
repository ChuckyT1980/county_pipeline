"""Debug why recorder searches return 0 results."""
import sys, json, time
sys.path.insert(0, ".")

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

with open("tyler_session_cookies.json") as f:
    cookies = json.load(f)

p = sync_playwright().__enter__()
b = p.chromium.launch(headless=True)
ctx = b.new_context(viewport={"width": 1280, "height": 900})
ctx.add_cookies(cookies)
page = ctx.new_page()
page.set_default_timeout(15000)

# Go to search
page.goto("https://recorder.buttecounty.net/web/search/DOCSEARCH481S1", wait_until="networkidle", timeout=20000)
time.sleep(3)
print(f"URL: {page.url}")

# Check if search field exists
field = page.query_selector("#field_BothNamesID")
print(f"Search field exists: {field is not None}")

# Check page text
body = page.inner_text("body")
print(f"Body text (first 500 chars): {body[:500]}")

# Try filling and searching
if field:
    field.fill("2585 ORO DAM LLC")
    time.sleep(1)
    page.keyboard.press("Escape")
    time.sleep(1)
    
    # Click search button
    btn = page.query_selector("#searchButton")
    if not btn:
        btn = page.query_selector('button:has-text("Search")')
    print(f"Search button: {btn is not None}")
    if btn:
        btn.click()
        time.sleep(5)
        print(f"After search URL: {page.url}")
        
        # Check for results or error
        body2 = page.inner_text("body")
        print(f"Body text after search (first 500 chars): {body2[:500]}")
        
        rows = page.query_selector_all("li.ss-search-row")
        print(f"Result rows: {len(rows)}")

b.close()
p.stop()
