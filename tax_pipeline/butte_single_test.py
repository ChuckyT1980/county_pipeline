"""
Minimal Butte Recorder Test — single document, heavy debug output.
"""
import sys, time
sys.path.insert(0, "..")
from playwright.sync_api import sync_playwright
from tax_pipeline.recorder_config import RECORDER_CONFIG

cfg = RECORDER_CONFIG["butte"]
disclaimer_sel = cfg["disclaimer_selector"]

print("1. Launching browser...")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_default_timeout(15000)

    print(f"2. Going to doc search: {cfg['doc_search_url']}")
    page.goto(cfg["doc_search_url"], wait_until="networkidle", timeout=30000)
    print(f"   URL after goto: {page.url}")
    page.wait_for_timeout(2000)

    if page.query_selector(disclaimer_sel):
        print("3. Disclaimer found, clicking...")
        page.click(disclaimer_sel, force=True)
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")
        print(f"   URL after disclaimer: {page.url}")
        if "DOCSEARCH" not in page.url:
            print("   Navigating back to doc search...")
            page.goto(cfg["doc_search_url"], wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)
            print(f"   URL: {page.url}")
    else:
        print("3. No disclaimer found")

    print(f"4. Looking for {cfg['doc_search_field']}...")
    try:
        page.wait_for_selector(cfg["doc_search_field"], timeout=10000)
        print(f"   FOUND: {cfg['doc_search_field']}")
    except Exception as e:
        print(f"   NOT FOUND: {e}")
        print(f"   Current URL: {page.url}")
        # Dump page content for debug
        content = page.content()
        print(f"   Page title: {page.title()}")
        print(f"   Page has 'search': {'search' in content.lower()}")
        print(f"   Page has 'disclaimer': {'disclaimer' in content.lower()}")
        browser.close()
        sys.exit(1)

    doc = "2024-0030607"
    print(f"5. Filling doc number: {doc}")
    page.fill(cfg["doc_search_field"], doc)
    page.click(cfg["search_button"])
    print("   Clicked search, waiting for results...")

    try:
        page.wait_for_url("**/web/searchResults/**", timeout=15000)
        print(f"   URL: {page.url}")
    except:
        print(f"   No URL change. Current: {page.url}")

    page.wait_for_timeout(3000)
    elements = page.query_selector_all(cfg["results_selector"])
    print(f"6. Results: {len(elements)} element(s) with selector '{cfg['results_selector']}'")

    if elements:
        text = elements[0].inner_text()
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        print(f"   First result lines:")
        for ln in lines[:15]:
            print(f"     {ln}")
        
        # Extract grantee
        grantee = None
        for j, ln in enumerate(lines):
            if "Grantee" in ln and j + 1 < len(lines):
                grantee = lines[j+1]
                break
        print(f"\n7. Grantee: {grantee}")

        if grantee:
            print(f"8. Name search for '{grantee}'...")
            page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            try:
                page.wait_for_selector(cfg["search_field"], timeout=10000)
                print(f"   FOUND: {cfg['search_field']}")
            except Exception as e:
                print(f"   NOT FOUND: {e}")
                browser.close()
                sys.exit(1)

            page.fill(cfg["search_field"], grantee)
            page.click(cfg["search_button"])
            print("   Clicked search, waiting...")

            try:
                page.wait_for_url("**/web/searchResults/**", timeout=15000)
            except:
                pass

            page.wait_for_timeout(3000)
            name_elements = page.query_selector_all(cfg["results_selector"])
            print(f"9. Name search results: {len(name_elements)} record(s)")
            if name_elements:
                for ne in name_elements[:3]:
                    t = ne.inner_text()
                    ls = [l.strip() for l in t.split("\n") if l.strip()]
                    print(f"   > {ls[0] if ls else '?'}")
    else:
        print("   No results. Dumping page snippet...")
        html = page.content()
        print(html[:2000])

    browser.close()
    print("\nDONE")
