"""
Test: verify name search works via JS form submit vs Playwright click.
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

    # Load name search
    print("1. Loading name search page...")
    page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    accept_disclaimer(page)
    if "DOCSEARCH481S1" not in page.url:
        page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
    page.wait_for_selector(cfg["search_field"], timeout=10000)

    page.fill(cfg["search_field"], "SAUTTER")

    # Approach 1: page.click on the <a> tag
    print("\nApproach 1: page.click('#searchButton')...")
    page.click(cfg["search_button"])
    page.wait_for_timeout(5000)
    url1 = page.url
    res1 = len(page.query_selector_all(cfg["results_selector"]))
    print(f"  URL: {url1}, Results: {res1}")

    # Reset: go back to name search
    page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    accept_disclaimer(page)
    page.wait_for_selector(cfg["search_field"], timeout=10000)
    page.fill(cfg["search_field"], "SAUTTER")

    # Approach 2: JavaScript form submit
    print("\nApproach 2: JS form.requestSubmit()...")
    page.evaluate("""() => {
        const input = document.querySelector('#field_BothNamesID');
        const form = input ? input.closest('form') : null;
        if (form) form.requestSubmit();
    }""")
    page.wait_for_timeout(5000)
    page.wait_for_load_state("networkidle")
    url2 = page.url
    res2 = len(page.query_selector_all(cfg["results_selector"]))
    print(f"  URL: {url2}, Results: {res2}")

    # Reset
    page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    accept_disclaimer(page)
    page.wait_for_selector(cfg["search_field"], timeout=10000)
    page.fill(cfg["search_field"], "SAUTTER")

    # Approach 3: Navigate directly to searchResults URL with query params
    print("\nApproach 3: Direct GET to searchResults URL...")
    page.evaluate("""() => {
        window.location.href = '/web/searchResults/DOCSEARCH481S1';
    }""")
    page.wait_for_timeout(5000)
    page.wait_for_load_state("networkidle")
    url3 = page.url
    res3 = len(page.query_selector_all(cfg["results_selector"]))
    print(f"  URL: {url3}, Results: {res3}")

    # Reset
    page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    accept_disclaimer(page)
    page.wait_for_selector(cfg["search_field"], timeout=10000)
    page.fill(cfg["search_field"], "SAUTTER")

    # Approach 4: Playwright locator (resolves at click time, not at call time)
    print("\nApproach 4: page.locator('#searchButton').click()...")
    page.locator(cfg["search_button"]).click()
    page.wait_for_timeout(5000)
    page.wait_for_load_state("networkidle")
    url4 = page.url
    res4 = len(page.query_selector_all(cfg["results_selector"]))
    print(f"  URL: {url4}, Results: {res4}")

    # Reset
    page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    accept_disclaimer(page)
    page.wait_for_selector(cfg["search_field"], timeout=10000)
    page.fill(cfg["search_field"], "SAUTTER")

    # Approach 5: Click the href directly via JS
    print("\nApproach 5: JS: document.querySelector('#searchButton').click()...")
    page.evaluate("""() => {
        const btn = document.querySelector('#searchButton');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(5000)
    page.wait_for_load_state("networkidle")
    url5 = page.url
    res5 = len(page.query_selector_all(cfg["results_selector"]))
    print(f"  URL: {url5}, Results: {res5}")

    # Dump results for any approach that worked
    for name, url, res in [("p.click", url1, res1), ("JS submit", url2, res2),
                           ("direct GET", url3, res3), ("locator", url4, res4),
                           ("JS click", url5, res5)]:
        if res > 0:
            print(f"\n*** {name} worked! Results: {res} ***")

    browser.close()
    print("\nDONE")
