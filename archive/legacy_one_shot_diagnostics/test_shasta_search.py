from playwright.sync_api import sync_playwright
import time
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1', timeout=60000)
    page.wait_for_load_state('networkidle')
    if page.locator('#submitDisclaimerAccept').is_visible():
        page.locator('#submitDisclaimerAccept').click()
        time.sleep(3)
        page.wait_for_load_state('networkidle')
    
    print('Current URL:', page.url)
    print('Has field_BothNamesID:', page.locator('#field_BothNamesID').is_visible())
    print('Has field_selfservice_searchString:', page.locator('#field_selfservice_searchString').is_visible())
    
    print('Inputs on page:')
    for input_el in page.locator('input').all():
        print(f"  - id: {input_el.get_attribute('id')}, type: {input_el.get_attribute('type')}")
    
    b.close()
