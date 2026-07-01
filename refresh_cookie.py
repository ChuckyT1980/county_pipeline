from playwright.sync_api import sync_playwright

def refresh_cookie():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1")
        try:
            page.click("#submitDisclaimerAccept", timeout=5000)
            page.wait_for_load_state("networkidle")
        except:
            pass
        context.storage_state(path="tax_pipeline/eagleweb_state.json")
        browser.close()
        print("Refreshed cookie!")

if __name__ == "__main__":
    refresh_cookie()
