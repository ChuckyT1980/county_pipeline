from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    # Load the Butte recorder dashboard
    page.goto("https://recorder.buttecounty.net/web/action/ACTIONGROUP201S4", timeout=60000)
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(2)
    
    # Handle disclaimer if present
    disclaimer = page.locator("#submitDisclaimerAccept")
    if disclaimer.count() > 0 and disclaimer.is_visible(timeout=3000):
        print("Clicking disclaimer...")
        disclaimer.click()
        time.sleep(3)
    
    # Dump page content to find all search links
    content = page.content()
    with open("butte_dashboard.html", "w", encoding="utf-8") as f:
        f.write(content)
    
    # Extract all links with "search" or "DOCSEARCH"
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content, "html.parser")
    links = soup.find_all("a")
    print("=== All links ===")
    for a in links:
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if href and any(x in href.lower() for x in ["search", "doc", "parcel", "apn", "property", "party"]):
            print(f"  {text:40s} -> {href}")
        elif href and "DOCSEARCH" in href:
            print(f"  {text:40s} -> {href}")
    
    print("\n=== All sidebar/nav links ===")
    for a in links:
        href = a.get("href", "")
        if href and not href.startswith("#") and not href.startswith("javascript") and not href.startswith("/web/resources"):
            text = a.get_text(strip=True)
            if text and len(text) < 80:
                print(f"  {text:50s} -> {href}")
    
    browser.close()
