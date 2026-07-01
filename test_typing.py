from playwright.sync_api import sync_playwright
import time
import os

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    
    state_file = "tax_pipeline/eagleweb_state.json"
    if os.path.exists(state_file):
        context = browser.new_context(storage_state=state_file)
    else:
        context = browser.new_context()
        
    page = context.new_page()
    
    # Step 2: Go to search
    print("Navigating to search...")
    page.goto("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1")
    page.wait_for_selector('input[aria-label="Name"]', timeout=30000)
    time.sleep(2)
    
    # Step 3: Just like YOU do it manually — click field, type name
    print("Typing SOTO DANIEL...")
    page.locator('input[aria-label="Name"]').click()
    time.sleep(0.5)
    page.keyboard.type("SOTO DANIEL", delay=100)
    time.sleep(1)
    
    # Step 4: Take screenshot to see what happened
    page.screenshot(path="test.png")
    val = page.locator('input[aria-label="Name"]').input_value()
    print("Value in field:", repr(val))
    
    browser.close()
