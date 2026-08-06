from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    
    page.goto('https://recorderselfservice.shastacounty.gov/web/user/disclaimer#/web/search/DOCSEARCH4S1', timeout=60000)
    time.sleep(5)
    print(f'1. URL: {page.url}')
    
    # Find the visible I Accept button
    btn = page.locator('#submitDisclaimerAccept').and_(page.get_by_text('I Accept')).last
    print(f'2. Button exists: {btn.count() > 0}')
    if btn.count() > 0:
        print(f'   Visible: {btn.is_visible()}, disabled: {btn.is_disabled()}')
        btn.click()
        time.sleep(5)
        page.wait_for_load_state('networkidle', timeout=30000)
        print(f'3. URL after accept: {page.url}')
        
        time.sleep(3)
        
        # Save HTML to examine
        with open('shasta_after_accept_v2.html', 'w', encoding='utf-8') as f:
            f.write(page.content())
        print(f'4. Saved HTML ({len(page.content())} chars)')
        
        # Check for any input/field elements
        for sel in ['#field_BothNamesID', 'input', '#searchButton', '[name="BothNamesID"]',
                     '#docSearchCriteria', 'form input', '.ss-search-criteria', 'select']:
            els = page.locator(sel)
            count = els.count()
            if count > 0:
                for i in range(min(count, 5)):
                    try:
                        id_ = els.nth(i).get_attribute('id') or ''
                        nm = els.nth(i).get_attribute('name') or ''
                        typ = els.nth(i).get_attribute('type') or ''
                        vis = els.nth(i).is_visible(timeout=500)
                        print(f'   {sel}[{i}]: id="{id_[:20]}" name="{nm[:20]}" type="{typ}" visible={vis}')
                    except:
                        pass
        
        body = page.locator('body').text_content()[:300]
        print(f'5. Body: {body}')
    
    browser.close()
