from playwright.sync_api import sync_playwright
import time
import re
from bs4 import BeautifulSoup

def test_extract(page):
    url = "https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1"
    print(f"Navigating to {url}")
    page.goto(url, timeout=60000)
    
    for i in range(3):
        if "disclaimer" in page.url.lower() or "web" == page.url.rstrip("/").split("/")[-1]:
            print(f"Handling disclaimer (attempt {i+1})...")
            try:
                page.evaluate("""
                    const btn = document.getElementById('submitDisclaimerAccept');
                    if(btn) { btn.disabled = false; btn.click(); }
                """)
                page.wait_for_load_state("networkidle")
                time.sleep(2)
            except Exception as e:
                pass
            
            if "DOCSEARCH" not in page.url.upper():
                page.goto(url, timeout=30000)
                page.wait_for_load_state("networkidle")
                time.sleep(1)
                
        if "DOCSEARCH" in page.url.upper():
            break
            
    print("Filling search form...")
    page.fill("#field_BothNamesID", "SMITH JOHN", timeout=8000)
    time.sleep(0.5)
    page.click("#searchButton")
    time.sleep(4)
    
    try: 
        page.wait_for_selector(".ui-li-static", timeout=8000)
    except: 
        print("Wait for selector failed.")
        
    html = page.content()
    with open("scratch/shasta_results.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Saved HTML.")
            
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    context = browser.new_context()
    page = context.new_page()
    page.add_init_script("""
        const _orig = window.setTimeout;
        window.setTimeout = function(fn, delay, ...args) {
            if (delay > 1000) delay = 100;
            return _orig(fn, delay, ...args);
        };
    """)
    test_extract(page)
    browser.close()
