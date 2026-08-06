from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    
    page.goto('https://recorderselfservice.shastacounty.gov/web/', timeout=60000)
    page.wait_for_load_state('networkidle', timeout=30000)
    time.sleep(2)
    
    print(f'1. URL: {page.url}')
    
    # Check if button is disabled
    btn = page.locator('#submitDisclaimerAccept')
    if btn.is_visible(timeout=5000):
        disabled = page.eval_on_selector('#submitDisclaimerAccept', 'el => el.disabled')
        print(f'2. Button disabled: {disabled}')
        
        # Wait until enabled (Tyler has 5s timer)
        start = time.time()
        while time.time() - start < 15:
            disabled = page.eval_on_selector('#submitDisclaimerAccept', 'el => el.disabled')
            if not disabled:
                break
            time.sleep(0.5)
        print(f'   Waited {time.time() - start:.1f}s for button to enable')
        
        # Click accept
        print('3. Clicking Accept...')
        btn.click()
        time.sleep(5)
        page.wait_for_load_state('networkidle', timeout=30000)
        print(f'4. URL after click: {page.url}')
        
        # Try to trigger the redirect manually via JS
        print('5. Triggering redirect via JS...')
        result = page.evaluate('''() => {
            try {
                if (typeof selfservice !== 'undefined' && selfservice.redirect) {
                    selfservice.redirect('/web/search/DOCSEARCH4S1', true);
                    return 'redirect called';
                }
                // Fallback: set hash
                window.location.hash = '#/web/search/DOCSEARCH4S1';
                return 'hash set as fallback';
            } catch(e) {
                return 'error: ' + e.message;
            }
        }''')
        print(f'   JS result: {result}')
        time.sleep(5)
        page.wait_for_load_state('networkidle', timeout=30000)
        print(f'6. URL after redirect: {page.url}')
        
        # Check for search field
        field = page.locator('#field_BothNamesID')
        is_vis = field.is_visible(timeout=5000)
        print(f'7. Search field visible: {is_vis}')
        
        if is_vis:
            print('SUCCESS!')
        else:
            body = page.locator('body').text_content()
            print(f'   Body: {body[:300]}')
    
    browser.close()
