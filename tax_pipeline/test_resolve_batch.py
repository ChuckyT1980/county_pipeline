"""Quick test: resolve owners for first 5 APNs via doc_number→recorder search"""
import time
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Test APNs with known doc numbers from our data
test_cases = [
    ("002271003000", "2024R0030607", "2024-0030607"),
    ("002292001000", "2024R0016848", "2024-0016848"),
    ("003470002000", "2018R0038646", "2018-0038646"),
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    page.goto("https://recorder.buttecounty.net/web/search/DOCSEARCH481S2", timeout=60000)
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

    doc_field = page.locator("#field_DocumentNumberID")
    search_btn = page.locator("#searchButton")

    for apn, asr_doc, rec_doc in test_cases:
        print(f"\n=== APN: {apn} | Doc: {asr_doc} -> {rec_doc} ===")
        
        doc_field.fill(rec_doc, timeout=5000)
        time.sleep(0.5)
        search_btn.click()
        time.sleep(4)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(1)

        content = page.content()
        soup = BeautifulSoup(content, "html.parser")
        full_text = soup.get_text()

        if "No results found" in full_text:
            print("  NO RESULTS FOUND")
            continue

        # Extract full text in order
        lines = [l.strip() for l in full_text.split("\n") if l.strip()]
        
        # Show grantor/grantee area
        capture = False
        for line in lines:
            if "Grantor" in line or "Grantee" in line:
                capture = True
            if capture:
                print(f"  [{line[:80]}]")
                if "Filter" in line or "Showing page" in line or "Your cart" in line:
                    break

        # Also try to extract names near Grantor/Grantee
        print("\n  --- Structured extraction ---")
        grantee_name = None
        for i, line in enumerate(lines):
            if "Grantee" in line and len(line) < 30:
                # Look ahead for the name
                for j in range(i+1, min(i+5, len(lines))):
                    candidate = lines[j]
                    if candidate and not any(x in candidate for x in ["Clear", "Grantor", "Recording", "Document", "Filter", "Cart", "Showing", "("]):
                        grantee_name = candidate
                        break
        if grantee_name:
            print(f"  Grantee: {grantee_name}")
        else:
            print(f"  Could not extract Grantee name")
            # Print surrounding context
            for i, line in enumerate(lines):
                if "Grantee" in line:
                    print(f"  Context around Grantee:")
                    for j in range(max(0,i-1), min(len(lines), i+6)):
                        print(f"    L{j}: [{lines[j][:80]}]")

    browser.close()
