from playwright.sync_api import sync_playwright

def test_extract(page):
    url = "https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1"
    page.goto(url, timeout=60000)
    page.wait_for_load_state("networkidle")
    
    if "disclaimer" in page.url.lower():
        try:
            page.evaluate("""
                const btn = document.getElementById('submitDisclaimerAccept');
                if(btn) { btn.disabled = false; btn.click(); }
            """)
            page.wait_for_load_state("networkidle")
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle")
            time.sleep(2)
        except:
            pass
            
    if "DOCSEARCH" not in page.url.upper():
        page.goto(url, timeout=30000)
        page.wait_for_load_state("networkidle")
        
    print("URL:", page.url)
    inputs = page.evaluate("Array.from(document.querySelectorAll('input')).map(i => i.id + ' (' + i.type + ')')")
    print("Inputs:", inputs)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    context = browser.new_context()
    page = context.new_page()
    test_extract(page)
    browser.close()
