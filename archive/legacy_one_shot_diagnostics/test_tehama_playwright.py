from playwright.sync_api import sync_playwright
try:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.goto('https://recordsearch.tehama.gov/web/search/DOCSEARCH4S2')
        page.wait_for_timeout(3000)
        btn = page.query_selector('a:has-text("Accept")')
        if not btn: btn = page.query_selector('button:has-text("Accept")')
        if not btn: btn = page.query_selector('#submitDisclaimerAccept')
        if btn:
            print("Clicking disclaimer")
            btn.click(force=True)
            page.wait_for_timeout(3000)
        
        field = page.query_selector('#field_DocumentNumberID')
        print('Field found directly:', bool(field))
        if not field:
            page.screenshot(path='tehama_failed.png')
            print('Saved tehama_failed.png')
            print(page.url)
            print(page.title())
        b.close()
except Exception as e:
    print('Error:', e)
