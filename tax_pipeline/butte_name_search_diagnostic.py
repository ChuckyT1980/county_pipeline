"""
Deep name search diagnostic: dump full page HTML after name search to
understand why results are empty. Test with a name known to have records.
"""
import sys
sys.path.insert(0, "..")
from playwright.sync_api import sync_playwright
from tax_pipeline.recorder_config import RECORDER_CONFIG

cfg = RECORDER_CONFIG["butte"]
disclaimer_sel = cfg["disclaimer_selector"]

def accept_disclaimer(page):
    if page.query_selector(disclaimer_sel):
        page.click(disclaimer_sel, force=True)
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_default_timeout(15000)

    # Start at name search page
    print("1. Loading name search page...")
    page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    accept_disclaimer(page)
    if "DOCSEARCH481S1" not in page.url:
        print(f"   Redirected to: {page.url}. Navigating back...")
        page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
    print(f"   URL: {page.url}")

    # Verify search field exists
    page.wait_for_selector(cfg["search_field"], timeout=10000)
    print(f"   Search field found: {cfg['search_field']}")

    # Test 1: Common name that likely has many records
    test_name = "SMITH"
    print(f"\n2. Searching for '{test_name}'...")
    page.fill(cfg["search_field"], test_name)
    page.click(cfg["search_button"])

    # Wait with generous timeout
    print("   Waiting for results...")
    try:
        page.wait_for_url("**/web/searchResults/**", timeout=15000)
        print(f"   URL changed to: {page.url}")
    except:
        print(f"   URL did NOT change. Current: {page.url}")

    page.wait_for_timeout(5000)
    page.wait_for_load_state("networkidle")
    print(f"   Final URL: {page.url}")

    # Check for results
    results = page.query_selector_all(cfg["results_selector"])
    print(f"   Results with '{cfg['results_selector']}': {len(results)}")

    # Also try other selectors
    alt_selectors = [".ui-li-static", "li[data-documentid]", ".ss-search-row", "li"]
    for sel in alt_selectors:
        alt = page.query_selector_all(sel)
        if alt:
            print(f"   Results with '{sel}': {len(alt)}")

    if not results:
        # Dump page structure for debug
        print("\n--- Page title ---")
        print(f"   {page.title()}")
        print("\n--- URL ---")
        print(f"   {page.url}")

        # Check if we're on a disclaimer or error page
        body_text = page.evaluate("() => document.body ? document.body.innerText.substring(0, 2000) : 'NO BODY'")
        print("\n--- Page body (first 2000 chars) ---")
        print(body_text)

        # Check for h1 elements
        h1s = page.query_selector_all("h1")
        print(f"\n--- h1 elements: {len(h1s)} ---")
        for h in h1s[:5]:
            print(f"   '{h.inner_text()}'")

        # Check for any list items
        lis = page.query_selector_all("li")
        print(f"\n--- li elements: {len(lis)} ---")
        for li in lis[:10]:
            t = li.inner_text().strip()
            if t:
                print(f"   '{t[:100]}'")
    else:
        # Show first few results
        for r in results[:3]:
            text = r.inner_text()
            ls = [l.strip() for l in text.split("\n") if l.strip()]
            print(f"   > {' / '.join(ls[:3])}")

    # Test 2: Navigate fresh to name search, try the grantee
    print("\n3. Fresh navigate to name search, try 'SAUTTER'...")
    page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    accept_disclaimer(page)
    if "DOCSEARCH481S1" not in page.url:
        page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

    page.wait_for_selector(cfg["search_field"], timeout=10000)
    page.fill(cfg["search_field"], "SAUTTER")
    page.click(cfg["search_button"])

    try:
        page.wait_for_url("**/web/searchResults/**", timeout=15000)
        print(f"   URL: {page.url}")
    except:
        print(f"   No URL change: {page.url}")

    page.wait_for_timeout(5000)
    page.wait_for_load_state("networkidle")

    results2 = page.query_selector_all(cfg["results_selector"])
    print(f"   Results: {len(results2)}")
    for r in results2[:5]:
        text = r.inner_text()
        ls = [l.strip() for l in text.split("\n") if l.strip()]
        print(f"   > {' / '.join(ls[:3])}")

    if not results2:
        body_text = page.evaluate("() => document.body ? document.body.innerText.substring(0, 1000) : 'NO BODY'")
        print(f"\n   Body: {body_text[:500]}")

    browser.close()
    print("\nDONE")
