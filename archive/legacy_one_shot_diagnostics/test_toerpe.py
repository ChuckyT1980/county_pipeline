from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time

def test_toerpe():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(storage_state="tax_pipeline/eagleweb_state.json")
        page = context.new_page()
        page.goto("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1")
        time.sleep(2)
        
        try:
            if page.locator("#submitDisclaimerAccept").is_visible(timeout=2000):
                page.click("#submitDisclaimerAccept")
                page.wait_for_load_state("networkidle")
        except:
            pass
            
        page.fill("#field_BothNamesID", "TOERPE MATTHEW")
        page.click("#searchButton")
        time.sleep(8)
        page.screenshot(path="debug_search.png")
        
        soup = BeautifulSoup(page.content(), "html.parser")
        results = soup.find_all("li", class_="ui-li-static")
        found = False
        for i, li in enumerate(results):
            text = li.text.upper()
            print(f"--- RESULT {i} ---")
            print(repr(text))
            
            if "GRANT DEED" in text or "QUITCLAIM" in text or "DEED" in text:
                found = True
        
        if not found:
            print("No deeds found.")
            
        browser.close()

if __name__ == "__main__":
    test_toerpe()
