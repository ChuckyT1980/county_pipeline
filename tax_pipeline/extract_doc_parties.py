from playwright.sync_api import sync_playwright
import time
from bs4 import BeautifulSoup
import re

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
    
    handle_disclaimer("https://recorder.buttecounty.net/web/search/DOCSEARCH481S2")
    
    doc_field = page.locator("#field_DocumentNumberID")
    doc_field.fill("2024-0030607", timeout=5000)
    time.sleep(0.5)
    
    search_btn = page.locator("#searchButton")
    search_btn.click()
    time.sleep(5)
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(3)  # Extra time for JS rendering
    
    # Get the full page content
    content = page.content()
    with open("butte_doc_result_detail.html", "w", encoding="utf-8") as f:
        f.write(content)
    
    soup = BeautifulSoup(content, "html.parser")
    full_text = soup.get_text()
    
    # Dump ALL text content to look for parties
    print("=== FULL PAGE TEXT ===")
    lines = full_text.split('\n')
    for i, line in enumerate(lines):
        clean = line.strip()
        if clean and len(clean) > 3:
            print(f"  {i:3d}: {clean[:200]}")
    
    # Also try to extract using JavaScript for dynamically loaded content
    print("\n=== JS evaluation ===")
    try:
        # Look for result items via JS
        result_texts = page.evaluate("""
            () => {
                const results = document.querySelectorAll('.ui-li-static, .ss-search-result, [data-role="listview"] li, .ss-listview li');
                return Array.from(results).slice(0, 10).map(el => el.textContent.trim().substring(0, 300));
            }
        """)
        for i, t in enumerate(result_texts):
            if t and len(t) > 5:
                print(f"  [{i}] {t}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Check for the search results container specifically
    print("\n=== Results container ===")
    try:
        results_html = page.evaluate("""
            () => {
                const el = document.getElementById('SelfService-1783521577293-search-results');
                return el ? el.innerHTML.substring(0, 3000) : 'not found';
            }
        """)
        print(results_html[:2000])
    except Exception as e:
        print(f"Error: {e}")
    
    # List all IDs with 'result' or 'search' in name
    print("\n=== All IDs with result/search ===")
    try:
        ids = page.evaluate("""
            () => {
                const all = document.querySelectorAll('[id*=\"result\"], [id*=\"Result\"], [id*=\"search\"], [id*=\"Search\"]');
                return Array.from(all).map(el => el.id + ' -> ' + (el.textContent || '').trim().substring(0, 100)).join('\\n');
            }
        """)
        print(ids[:2000])
    except Exception as e:
        print(f"Error: {e}")
    
    browser.close()
