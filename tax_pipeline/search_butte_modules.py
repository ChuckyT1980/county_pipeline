from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    page.goto("https://recorder.buttecounty.net/web/action/ACTIONGROUP481S1", timeout=60000)
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(2)
    
    disclaimer = page.locator("#submitDisclaimerAccept")
    if disclaimer.count() > 0 and disclaimer.is_visible(timeout=3000):
        disclaimer.click()
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(2)
    
    content = page.content()
    with open("butte_actiongroup481.html", "w", encoding="utf-8") as f:
        f.write(content)
    
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content, "html.parser")
    
    print("=== Links on ACTIONGROUP481S1 ===")
    for a in soup.find_all("a"):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if href and "DOCSEARCH" in href:
            print(f"  {text:50s} -> {href}")
    
    print("\n=== All action links ===")
    for a in soup.find_all("a"):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if text and len(text) < 100 and href and ("search" in href.lower() or "DOC" in href or href.startswith("/web/action")):
            print(f"  {text:50s} -> {href}")
    
    # Also try common ParcelSearch or PropertySearch IDs  
    for search_type in ["PARCELSEARCH", "PROPERTYSEARCH", "DOCSEARCH", "PARTYSEARCH"]:
        for i in range(480, 485):
            url = f"https://recorder.buttecounty.net/web/search/{search_type}{i}S1"
            try:
                r = page.goto(url, timeout=10000)
                if r.status == 200:
                    print(f"\nFound: /web/search/{search_type}{i}S1 -> {r.status}")
                    soup2 = BeautifulSoup(page.content(), "html.parser")
                    # Find all form input fields
                    for inp in soup2.find_all("input"):
                        name = inp.get("name", "")
                        fid = inp.get("id", "")
                        itype = inp.get("type", "")
                        if name and itype not in ("hidden", "submit") and "field_" in name:
                            print(f"  Field: {name}")
            except:
                pass
    
    browser.close()
