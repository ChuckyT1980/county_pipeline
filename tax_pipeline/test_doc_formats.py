from playwright.sync_api import sync_playwright
import time, re
from bs4 import BeautifulSoup

apn = "002271003000"
doc_number = "2024R0030607"

# Try different formats
formats = [
    doc_number,                    # 2024R0030607
    doc_number.replace("R", "-"),  # 2024-0030607
    doc_number.replace("R", ""),   # 20240030607
    doc_number[5:],                # 0030607 (just the number part)
    doc_number[:4] + "-" + doc_number[5:],  # 2024-0030607
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    def handle_disclaimer(url):
        page.goto(url, timeout=60000)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(2)
        disclaimer = page.locator("#submitDisclaimerAccept")
        if disclaimer.count() > 0 and disclaimer.is_visible(timeout=2000):
            for _ in range(30):
                try:
                    disabled = page.eval_on_selector("#submitDisclaimerAccept", "btn => btn.disabled")
                    if not disabled:
                        disclaimer.click()
                        time.sleep(3)
                        break
                except:
                    pass
                time.sleep(0.5)
    
    # Navigate to Document Number Search
    handle_disclaimer("https://recorder.buttecounty.net/web/search/DOCSEARCH481S2")
    
    for fmt in formats:
        print(f"\n=== Trying: {fmt} ===")
        
        doc_field = page.locator("#field_DocumentNumberID")
        if doc_field.count() > 0:
            doc_field.fill(fmt, timeout=5000)
            time.sleep(0.5)
            
            search_btn = page.locator("#searchButton")
            if search_btn.count() > 0:
                search_btn.click()
                time.sleep(5)
                page.wait_for_load_state("networkidle", timeout=15000)
                
                content = page.content()
                soup = BeautifulSoup(content, "html.parser")
                full_text = soup.get_text()
                
                # Check for results vs no results
                if "No results found" in full_text:
                    print("  -> No results found")
                elif "Your cart is empty" in full_text and "No results" not in full_text:
                    # Check for result items
                    results = soup.find_all("li", class_="ui-li-static")
                    real_results = [li for li in results if li.get_text(strip=True) and len(li.get_text(strip=True)) > 30]
                    if real_results:
                        print(f"  -> FOUND {len(real_results)} results!")
                        for li in real_results[:3]:
                            print(f"     {li.get_text(strip=True)[:200]}")
                    else:
                        print(f"  -> Empty results")
                else:
                    # Check for any document data
                    print(f"  -> Checking for data in page...")
                    for li in soup.find_all("li"):
                        text = li.get_text(strip=True)
                        if text and 'By:' in text or 'GRANT' in text or 'NAME' in text or 'PARTY' in text or doc_number[:4] in text:
                            print(f"     MATCH: {text[:200]}")
                    print(f"  -> No results (empty)")
    
    browser.close()
