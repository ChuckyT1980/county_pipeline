from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Use our saved cookie state!
        context = browser.new_context(storage_state="tax_pipeline/eagleweb_state.json")
        page = context.new_page()
        
        # Test 1: Go to the deep link
        url = "https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1?BothNamesID=TOERPE+MATTHEW"
        page.goto(url)
        page.wait_for_timeout(3000)
        
        print(f"Current URL: {page.url}")
        html = page.content()
        if "TOERPE" in html:
            print("Found TOERPE in HTML")
        else:
            print("Did not find TOERPE. Check if search form is prefilled.")
            
        browser.close()

if __name__ == "__main__":
    run()
