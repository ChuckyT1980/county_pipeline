"""
Playwright probe for GovEase Kern County Auction 1348
Inspect page DOM, buttons, forms, tables, links, and frame content.
"""
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time, os

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()

        url = "https://liveauctions.govease.com/PublicPortal/RegistrationDetail?AuctionID=1348&Edit=False/"
        print(f"Navigating to {url}")
        page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(3)

        print("Page title:", page.title())

        # Save full page HTML
        html = page.content()
        with open(r"C:\Users\chuck\Downloads\county_pipeline\kern\govease_reg_1348.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("Saved full page HTML.")

        soup = BeautifulSoup(html, "html.parser")
        
        # Check for any buttons or links
        buttons = page.eval_on_selector_all("button, input[type='button'], input[type='submit'], a.btn", 
            "els => els.map(e => ({text: e.innerText.trim(), id: e.id, class: e.className, href: e.href||''}))")
        print(f"Interactive elements count: {len(buttons)}")
        for b in buttons:
            print("  BTN:", b)

        # Check forms
        forms = soup.find_all("form")
        print(f"Forms count: {len(forms)}")
        for f in forms:
            print("  FORM action:", f.get("action"), "id:", f.get("id"), "method:", f.get("method"))

        # Look for links to tax sale properties or catalog
        links = soup.find_all("a")
        for l in links:
            t = l.text.strip()
            h = l.get("href", "")
            if t or h:
                print(f"  LINK: '{t}' -> '{h}'")

        browser.close()

if __name__ == "__main__":
    run()
