"""
Test: POST to searchPost endpoints directly to see if name search requires auth.
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

    # First, do the doc search that we know works — establish session
    print("1. Establishing session via doc search...")
    page.goto(cfg["doc_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    accept_disclaimer(page)
    if "DOCSEARCH481S2" not in page.url:
        page.goto(cfg["doc_search_url"], wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

    page.wait_for_selector(cfg["doc_search_field"], timeout=10000)
    page.fill(cfg["doc_search_field"], "2024-0030607")
    page.click(cfg["search_button"])
    try:
        page.wait_for_url("**/web/searchResults/DOCSEARCH481S2*", timeout=15000)
    except:
        pass
    page.wait_for_timeout(3000)
    page.wait_for_load_state("networkidle")
    results = page.query_selector_all(cfg["results_selector"])
    print(f"   Doc search results: {len(results)} (should be 1)")

    # Now try name search in SAME session
    print("\n2. Name search in same session (already accepted disclaimer)...")
    page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    # Check for disclaimer
    if page.query_selector(disclaimer_sel):
        page.click(disclaimer_sel, force=True)
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

    page.wait_for_selector(cfg["search_field"], timeout=10000)
    page.fill(cfg["search_field"], "SMITH")

    # Intercept the POST to see what happens
    print("   Setting up request/response listener...")
    responses = []
    def on_response(response):
        if "searchPost" in response.url or "searchResults" in response.url:
            responses.append({
                "url": response.url,
                "status": response.status,
                "headers": dict(response.headers) if response.headers else {}
            })
            try:
                body = response.text()
                has_results = "ss-search-row" in body
                print(f"   Response: {response.url} status={response.status} has_results={has_results}")
                if not has_results:
                    # Check what page was returned
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(body, "html.parser")
                    title = soup.title.string if soup.title else "NO TITLE"
                    print(f"     Page title: {title}")
                    login_link = soup.find("a", string=lambda t: t and "log in" in t.lower() if t else False)
                    if login_link:
                        print(f"     Login link found: {login_link.get('href', '')}")
            except:
                pass

    page.on("response", on_response)

    # Click search
    page.click(cfg["search_button"])
    page.wait_for_timeout(5000)
    page.wait_for_load_state("networkidle")

    print(f"\n   Final URL: {page.url}")
    print(f"   Captured {len(responses)} responses")

    # Check results
    results = page.query_selector_all(cfg["results_selector"])
    print(f"   Results: {len(results)}")

    # Now try: navigate to name search results URL directly with POST params
    print("\n3. Try direct POST to name search...")
    page.evaluate("""async () => {
        const form = document.querySelector('form[action*="searchPost/DOCSEARCH481S1"]');
        if (form) {
            const fd = new FormData(form);
            fd.set('field_BothNamesID', 'SMITH');
            const resp = await fetch('/web/searchPost/DOCSEARCH481S1', {method: 'POST', body: fd});
            const html = await resp.text();
            return {
                status: resp.status,
                hasResults: html.includes('ss-search-row'),
                titleMatch: html.match(/<title>(.*?)<\/title>/)?.[1] || 'none',
                snippet: html.substring(0, 500)
            };
        }
        return 'no form found';
    }""")

    browser.close()
    print("\nDONE")
