import time
from playwright.sync_api import sync_playwright

def run_debug():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        login_url = "https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1"
        page.goto(login_url, timeout=60000)
        page.wait_for_load_state("networkidle")
        
        try:
            if page.locator("#submitDisclaimerAccept").is_visible(timeout=5000):
                page.locator("#submitDisclaimerAccept").click()
                page.wait_for_load_state("networkidle")
        except Exception:
            pass
            
        time.sleep(2)
        
        html = page.content()
        with open("shasta_search_page.html", "w", encoding="utf-8") as f:
            f.write(html)
            
        browser.close()

if __name__ == "__main__":
    run_debug()
