from playwright.sync_api import sync_playwright
import time
import os

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state="tax_pipeline/eagleweb_state.json")
        page = context.new_page()
        
        page.goto("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        
        page.screenshot(path="debug1.png")
        
        # Try to fill
        try:
            name_input = page.locator("input#field_BothNamesID").first
            name_input.wait_for(state="visible", timeout=5000)
            def handle_request(request):
                if request.method == 'POST' and 'search' in request.url:
                    print("API URL:", request.url)
                    print("API Payload:", request.post_data)
            
            page.on("request", handle_request)
            
            name_input.click()
            name_input.type("SOTO", delay=100)
            
            # Click the search button explicitly
            page.click("a#searchButton")
            
            page.wait_for_load_state("networkidle")
            time.sleep(3)
            
            with open("debug.html", "w", encoding="utf-8") as f:
                f.write(page.content())
        except Exception as e:
            print("Failed:", e)
            
        browser.close()

if __name__ == "__main__":
    test()
