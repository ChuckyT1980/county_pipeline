from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    page.goto("https://common2.mptsweb.com/MBC/butte/tax/search", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)
    
    # Dump ALL visible elements on the page
    print("=== All visible input elements ===")
    inputs = page.locator("input:visible")
    for i in range(inputs.count()):
        el = inputs.nth(i)
        print(f"  [{i}] id={el.get_attribute('id')} name={el.get_attribute('name')} type={el.get_attribute('type')} placeholder={el.get_attribute('placeholder')}")
    
    print("\n=== All visible buttons/links ===")
    btns = page.locator("a:visible, button:visible, input[type='submit']:visible, input[type='button']:visible")
    for i in range(btns.count()):
        el = btns.nth(i)
        print(f"  [{i}] tag={el.evaluate('e => e.tagName')} id={el.get_attribute('id')} text={el.inner_text()[:60]}")
    
    print("\n=== Page title and URL ===")
    print(f"URL: {page.url}")
    print(f"Title: {page.title()}")
    
    # Check if there's any search form with visible fields
    # The #searchForm elements might be in tabs or hidden sections
    print("\n=== #searchForm content ===")
    sf = page.locator("#searchForm")
    if sf.count() > 0:
        sf_html = sf.inner_html()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(sf_html, "html.parser")
        for inp in soup.find_all("input"):
            print(f"  id={inp.get('id','')} name={inp.get('name','')} type={inp.get('type','')}")
        for sel in soup.find_all("select"):
            print(f"  SELECT id={sel.get('id','')} name={sel.get('name','')}")
    
    browser.close()
