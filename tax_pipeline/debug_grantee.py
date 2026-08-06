import requests
from bs4 import BeautifulSoup

# Test doc number search result HTML directly
url = "https://recorder.buttecounty.net/web/search/DOCSEARCH481S2"
doc = "2012-0044824"

# Can't easily get the search result page content via requests (it's JS-rendered)
# Let's use a different approach - check the grantee extraction logic

# The issue might be the "Grantee" detection. Let me look at a sample
# from the original resolve_butte_owners.py which DID work (460/504 names)

# Actually, let me look at what the original resolve script did differently.
# In resolve_butte_owners.py line 130-143:
# It looks for "Grantee" in a clean line, then looks ahead for the name.

# Possible issues:
# 1. The DOCSEARCH481S2 form might not have loaded properly
# 2. The page might have returned an error
# 3. The text parsing might fail on these parcels

# Let me try to fetch one page manually with playwright
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, timeout=60000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)
    
    # Handle disclaimer
    disc = page.locator("#submitDisclaimerAccept")
    if disc.count() > 0:
        for _ in range(30):
            try:
                disabled = page.eval_on_selector("#submitDisclaimerAccept", "btn => btn.disabled")
                if not disabled:
                    disc.click()
                    time.sleep(3)
                    break
            except:
                pass
            time.sleep(0.5)
    
    # Enter doc number
    page.fill("#field_DocumentNumberID", doc, timeout=5000)
    time.sleep(0.3)
    page.locator("#searchButton").click()
    time.sleep(5)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)
    
    # Get the page content
    html = page.content()
    
    # Save for analysis
    with open("debug_grantee.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print("Saved debug_grantee.html (%d bytes)" % len(html))
    
    # Try the extraction
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text(" ", strip=True)
    print("\nFull text (first 2000 chars):")
    print(full_text[:2000])
    
    # Check for specific patterns
    print("\n\n'No results found':", "No results found" in full_text)
    print("'GRANTEE' in text:", "GRANTEE" in full_text.upper())
    print("'Grantee' in text:", "Grantee" in full_text)
    
    # Look for the table
    print("\nLooking for Grantee in lines:")
    lines = full_text.split("\n")
    for i, line in enumerate(lines):
        clean = line.strip()
        if "grantee" in clean.lower():
            print(f"  Line {i}: '{clean[:100]}'")
            # Print surrounding lines
            for j in range(max(0,i-2), min(len(lines), i+5)):
                print(f"    +{j}: '{lines[j].strip()[:100]}'")
    
    browser.close()
