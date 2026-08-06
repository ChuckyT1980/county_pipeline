from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    print("Navigating to disclaimer...")
    page.goto("https://recorderselfservice.shastacounty.gov/web/user/disclaimer")
    time.sleep(2)
    try:
        page.click("#submitDisclaimerAccept")
        time.sleep(2)
        print("Disclaimer accepted.")
    except Exception as e:
        print("Disclaimer accept failed or not found:", e)
    
    print("Navigating to search...")
    # Trying the working url from the probe
    page.goto("https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1")
    time.sleep(2)
    
    print("Searching for KRIEG ALEX...")
    page.fill("#field_BothNamesID", "KRIEG ALEX")
    page.click("input[type='submit'][value='Search']")
    time.sleep(4)
    
    # Save the results HTML
    with open("shasta_tyler_results.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    print("Saved shasta_tyler_results.html")
    browser.close()
