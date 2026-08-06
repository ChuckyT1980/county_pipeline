from playwright.sync_api import sync_playwright
import time
import re
from bs4 import BeautifulSoup

def test_extract(page):
    url = "https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1"
    print(f"Navigating to {url}")
    page.goto(url, timeout=60000)
    
    # Handle disclaimer loop - sometimes it redirects
    for i in range(3):
        if "disclaimer" in page.url.lower() or "web" == page.url.rstrip("/").split("/")[-1]:
            print(f"Handling disclaimer (attempt {i+1})...")
            try:
                page.wait_for_selector("#submitDisclaimerAccept", timeout=5000)
                page.click("#submitDisclaimerAccept")
                page.wait_for_load_state("networkidle")
                time.sleep(2)
            except Exception as e:
                print(f"Disclaimer click failed: {e}")
                
        if "DOCSEARCH" in page.url.upper():
            break
            
    print(f"Current URL: {page.url}")
    
    if "DOCSEARCH" not in page.url.upper():
        print("Failed to reach search page.")
        return
        
    print("Filling search form...")
    page.fill("#field_BothNamesID", "SMITH JOHN", timeout=8000)
    time.sleep(0.5)
    page.click("#searchButton")
    time.sleep(4)
    
    try: 
        page.wait_for_selector(".ui-li-static", timeout=8000)
    except: 
        print("No results found.")
        return
        
    soup = BeautifulSoup(page.content(), "html.parser")
    docs = soup.find_all("li", class_="ui-li-static")
    print(f"Found {len(docs)} documents.")
    
    deed_link = None
    for li in docs:
        text = li.text.strip().upper()
        if "DEED" in text and not ("DEED OF TRUST" in text or "TRUST DEED" in text):
            a_tag = li.find("a")
            if a_tag and a_tag.get("href"):
                deed_link = a_tag["href"]
                print(f"Found Deed Link: {deed_link}")
                break
                
    if deed_link:
        if deed_link.startswith('/'):
            domain = "/".join(url.split("/")[:3])
            deed_link = domain + deed_link
            
        print(f"Navigating to document details: {deed_link}")
        page.goto(deed_link)
        time.sleep(3)
        
        detail_html = page.content()
        soup = BeautifulSoup(detail_html, "html.parser")
        text_content = soup.get_text(separator=' ', strip=True)
        
        apn_match = re.search(r'APN[:\s]*([\d\-]+)', text_content, re.IGNORECASE)
        if apn_match:
            print(f"Found APN candidate: {apn_match.group(1)}")
        else:
            print("No obvious APN pattern found in detail text.")
            
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
