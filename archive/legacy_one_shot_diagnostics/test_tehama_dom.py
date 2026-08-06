from playwright.sync_api import sync_playwright
import time

def test_tehama():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        url = "https://recordsearch.tehama.gov/web/search/DOCSEARCH4S2"
        print(f"Loading {url}")
        page.goto(url, wait_until="networkidle")
        time.sleep(2)
        
        disclaimer_sel = "#submitDisclaimerAccept"
        if page.query_selector(disclaimer_sel):
            print("Accepting disclaimer...")
            page.evaluate(f"() => {{ const btn = document.querySelector('{disclaimer_sel}'); if(btn) btn.removeAttribute('disabled'); }}")
            page.click(disclaimer_sel, force=True)
            time.sleep(2)
            page.wait_for_load_state("networkidle")
            
            if "search" not in page.url.lower():
                page.goto(url, wait_until="networkidle")
                time.sleep(2)
                
        doc_input = "#field_DocumentNumberID"
        search_btn = "#searchButton"
        
        # Test: format 2018007697
        doc = "2018007697"
        print(f"\nSearching for {doc}...")
        page.fill(doc_input, doc)
        page.click(search_btn)
        time.sleep(5)
        page.wait_for_load_state("networkidle")
        
        # Dump HTML
        with open("tehama_results.html", "w", encoding="utf-8") as f:
            f.write(page.content())
            
        print("Saved tehama_results.html")
        
        # See if there is a 'no results' message
        print("Page Text snippet:")
        text = page.inner_text("body")
        for line in text.splitlines():
            if line.strip() and "search" not in line.lower() and "document" not in line.lower() and "tehama" not in line.lower():
                print(line.strip())

        browser.close()

test_tehama()
