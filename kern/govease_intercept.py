"""
GovEase Network Intercept via Playwright
Opens the actual GovEase auction property listing page,
intercepts every network request the site makes,
and captures the real API endpoint + response data with full property details.
"""
import os, json, time
import pandas as pd
from playwright.sync_api import sync_playwright

BASE = r"C:\Users\chuck\Downloads\county_pipeline\kern"
AUCTION_ID = 1348

captured_responses = []

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        # Intercept ALL responses
        def handle_response(response):
            url = response.url
            ct = response.headers.get("content-type", "")
            # Capture any JSON response
            if "json" in ct or "application/json" in ct:
                try:
                    body = response.json()
                    size = len(str(body))
                    if size > 100:
                        captured_responses.append({
                            "url": url,
                            "size": size,
                            "data": body
                        })
                        print(f"  [JSON] {url[:100]} | {size} chars")
                        if isinstance(body, list) and len(body) > 0:
                            print(f"         Array[{len(body)}] first keys: {list(body[0].keys())[:8] if isinstance(body[0], dict) else type(body[0])}")
                        elif isinstance(body, dict):
                            print(f"         Keys: {list(body.keys())[:8]}")
                except Exception:
                    pass
            # Also capture any large text responses that might be data
            elif response.status == 200 and any(k in url.lower() for k in ["property","parcel","lot","auction","apn"]):
                try:
                    text = response.text()
                    if len(text) > 200 and ("apn" in text.lower() or "parcel" in text.lower() or "owner" in text.lower()):
                        print(f"  [TEXT/PARCEL] {url[:100]} | {len(text)} chars")
                        print(f"  Sample: {text[:300]}")
                        captured_responses.append({"url": url, "size": len(text), "data": text})
                except Exception:
                    pass

        page.on("response", handle_response)

        # Try multiple GovEase pages for the Kern auction
        pages_to_try = [
            f"https://liveauctions.govease.com/PublicPortal/RegistrationDetail?AuctionID={AUCTION_ID}&Edit=False/",
            f"https://liveauctions.govease.com/PublicPortal/AuctionList",
            f"https://www.govease.com/auctions",
            f"https://liveauctions.govease.com/",
        ]

        for url in pages_to_try:
            print(f"\n>>> Loading: {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=20000)
                print(f"    Title: {page.title()}")
                print(f"    URL: {page.url}")
                time.sleep(2)

                # Look for links to property listings
                links = page.eval_on_selector_all("a[href]",
                    "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))")
                for l in links:
                    href = l.get("href","")
                    text = l.get("text","")
                    if any(k in href.lower() or k in text.lower()
                           for k in ["property","parcel","lot","kern","auction","1348","listing"]):
                        print(f"    LINK: {text[:50]} -> {href[:100]}")

                # Scroll to trigger lazy loading
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)
                page.evaluate("window.scrollTo(0, 0)")
                time.sleep(1)

            except Exception as e:
                print(f"    ERROR: {e}")

        # Try to find and click property listing links
        print("\n>>> Searching for property listing page...")
        try:
            page.goto(f"https://liveauctions.govease.com/PublicPortal/RegistrationDetail?AuctionID={AUCTION_ID}&Edit=False/",
                      wait_until="networkidle", timeout=15000)
            
            # Get all links on the page
            all_links = page.eval_on_selector_all("a[href]",
                "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))")
            print(f"  Total links on page: {len(all_links)}")
            for l in all_links:
                if len(l.get("text","").strip()) > 0:
                    print(f"  [{l.get('text','')[:40]}] -> {l.get('href','')[:100]}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # Save all captured API responses
        if captured_responses:
            print(f"\n=== CAPTURED {len(captured_responses)} API RESPONSES ===")
            for i, resp in enumerate(captured_responses):
                print(f"\n[{i}] {resp['url']}")
                print(f"    Size: {resp['size']}")
                # Save significant responses
                if resp['size'] > 500:
                    fname = os.path.join(BASE, f"govease_captured_{i}.json")
                    with open(fname, "w") as f:
                        json.dump(resp['data'], f, indent=2, default=str)
                    print(f"    Saved -> {fname}")
        else:
            print("\n=== NO API JSON RESPONSES CAPTURED ===")
            print("GovEase may use server-side rendering or a different data loading method.")

        browser.close()

if __name__ == "__main__":
    run()
