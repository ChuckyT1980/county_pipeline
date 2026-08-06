from playwright.sync_api import sync_playwright
import time, re, requests
from bs4 import BeautifulSoup

# Step 1: Get doc_number from AsrPrint on common1
apn = "002271003000"
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})
asr_url = f"https://common1.mptsweb.com/mbap/butte/asr/AsrPrint/{apn}"
r = s.get(asr_url, timeout=15)
soup = BeautifulSoup(r.text, "html.parser")
doc_number = None
for row in soup.find_all("tr"):
    cells = row.find_all(["td", "th"])
    if len(cells) >= 2:
        label = cells[0].get_text(strip=True)
        value = cells[1].get_text(strip=True)
        if "Current Document Number" in label:
            doc_number = value
            break
print(f"APN: {apn}")
print(f"Doc Number: {doc_number}")

if not doc_number:
    print("No document number found")
    exit()

# Step 2: Search Butte recorder by document number
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
    print("\n=== Navigating to Document Number Search ===")
    handle_disclaimer("https://recorder.buttecounty.net/web/search/DOCSEARCH481S2")
    
    print(f"URL: {page.url}")
    print(f"Title: {page.title()}")
    
    # Fill in the document number
    doc_field = page.locator("#field_DocumentNumberID")
    if doc_field.count() > 0:
        print(f"\nFilling document number: {doc_number}")
        doc_field.fill(doc_number, timeout=5000)
        time.sleep(1)
        
        # Click Search
        search_btn = page.locator("#searchButton")
        if search_btn.count() > 0:
            search_btn.click()
            time.sleep(5)
            page.wait_for_load_state("networkidle", timeout=30000)
            
            print(f"\nPost-search URL: {page.url}")
            
            # Extract results
            content = page.content()
            with open("butte_doc_search_results.html", "w", encoding="utf-8") as f:
                f.write(content)
            
            soup = BeautifulSoup(content, "html.parser")
            
            # Look for result items
            results = soup.find_all("li", class_="ui-li-static")
            print(f"\n=== Results ({len(results)} items) ===")
            for i, li in enumerate(results):
                text = li.get_text(strip=True)
                if text and len(text) > 10:
                    print(f"  [{i}] {text[:300]}")
            
            # Also check for any table/structured data
            for table in soup.find_all("table"):
                print(f"\nTable found:")
                for row in table.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                    print(f"  {' | '.join(cells)}")
            
            # Check for Grantor/Grantee or party names
            full_text = soup.get_text()
            for pattern in [r'GRANTOR[^.]*\.', r'GRANTEE[^.]*\.', r'[Pp]art(?:y|ies)[^.]*\.']:
                for m in re.finditer(pattern, full_text):
                    print(f"\nFound: {m.group()[:200]}")
    
    browser.close()
