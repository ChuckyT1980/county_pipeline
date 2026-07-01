from playwright.sync_api import sync_playwright
import time
from bs4 import BeautifulSoup

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Navigating to homepage...")
        page.goto("https://recordsearch.tehama.gov/web", timeout=60000)
        print("Waiting for network idle...")
        page.wait_for_load_state("networkidle")
        
        try:
            print("Clicking accept...")
            page.click("button#submitDisclaimerAccept", timeout=10000)
            page.wait_for_load_state("networkidle")
        except Exception as e:
            print("Could not accept disclaimer:", e)
            
        print("Searching...")
        page.goto("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1?lastName=SOTO&firstName=JOSE")
        page.wait_for_load_state("networkidle")
        
        try:
            page.click("a#searchButton", timeout=10000)
            print("Clicked search, waiting for results...")
            page.wait_for_load_state("networkidle")
            time.sleep(2)
        except Exception as e:
            print("Could not click search:", e)
            
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        results = soup.find_all("li", class_="ui-li-static")
        print(f"Found {len(results)} results")
        for r in results[:5]:
            print(r.text.strip()[:100])
            
        browser.close()

if __name__ == "__main__":
    main()
