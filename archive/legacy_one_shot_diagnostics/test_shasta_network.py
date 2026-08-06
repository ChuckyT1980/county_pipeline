from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def handle_request(req):
            if req.method == 'POST' and 'searchPost' in req.url:
                print(f"POST {req.url}")
                print(f"  Headers: {req.headers}")
                print(f"  Data: {req.post_data}")

        page.on('request', handle_request)
        print("Navigating to Shasta...")
        page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S5")
        page.wait_for_timeout(2000)
        
        # Accept disclaimer
        sel = "#submitDisclaimerAccept"
        if page.query_selector(sel):
            print("Accepting disclaimer...")
            page.evaluate('() => { let btn = document.querySelector("#submitDisclaimerAccept"); if (btn) btn.removeAttribute("disabled"); }')
            page.click(sel, force=True)
            page.wait_for_timeout(2000)
            page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S5")
            page.wait_for_timeout(2000)
            
        print("Filling form...")
        if page.query_selector("#field_DocumentNumberID"):
            page.fill("#field_DocumentNumberID", "2018-0007697") # Need a valid format for Shasta, hyphenated usually works
            page.click("#searchButton")
            
            print("Waiting for results...")
            try:
                page.wait_for_selector("li.ss-search-row", timeout=10000)
                print("Got results!")
            except Exception as e:
                print("Timeout waiting for results", e)
        else:
            print("Could not find search field. HTML snippet:")
            print(page.content()[:2000])
        time.sleep(1)
        browser.close()

if __name__ == "__main__":
    run()
