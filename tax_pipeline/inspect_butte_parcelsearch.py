from playwright.sync_api import sync_playwright
import time, json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    # First handle disclaimer on the official action group
    page.goto("https://recorder.buttecounty.net/web/action/ACTIONGROUP481S1", timeout=60000)
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(2)
    
    disclaimer = page.locator("#submitDisclaimerAccept")
    if disclaimer.count() > 0 and disclaimer.is_visible(timeout=2000):
        for _ in range(30):
            try:
                disabled = page.eval_on_selector("#submitDisclaimerAccept", "btn => btn.disabled")
                if not disabled:
                    disclaimer.click()
                    print("Disclaimer clicked")
                    time.sleep(3)
                    break
            except:
                pass
            time.sleep(0.5)
    
    # Now go to PARCELSEARCH directly
    print("\n=== Navigating to PARCELSEARCH481S1 ===")
    page.goto("https://recorder.buttecounty.net/web/search/PARCELSEARCH481S1", timeout=60000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(3)
    
    print(f"URL: {page.url}")
    print(f"Title: {page.title()}")
    
    # Save full HTML
    content = page.content()
    with open("butte_parcel_search.html", "w", encoding="utf-8") as f:
        f.write(content)
    
    # Dump ALL input fields
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content, "html.parser")
    
    print("\n=== All input elements ===")
    for inp in soup.find_all("input"):
        info = {a: inp.get(a, "") for a in ["id", "name", "type", "value", "placeholder", "class"]}
        if info.get("type") != "hidden" or info.get("value"):
            print(f"  {json.dumps(info)}")
    
    print("\n=== All hidden inputs ===")
    for inp in soup.find_all("input", type="hidden"):
        print(f"  {inp.get('name','')} = {inp.get('value','')[:80]}")
    
    print("\n=== All select elements ===")
    for sel in soup.find_all("select"):
        print(f"  id={sel.get('id','')} name={sel.get('name','')}")
        for opt in sel.find_all("option")[:5]:
            print(f"    {opt.get('value','')} -> {opt.get_text(strip=True)[:60]}")
    
    print("\n=== All form actions ===")
    for form in soup.find_all("form"):
        print(f"  id={form.get('id','')} action={form.get('action','')} method={form.get('method','')}")
    
    # Check page source for JavaScript references
    print("\n=== Network requests (monitoring) ===")
    page.on("request", lambda req: print(f"  REQ: {req.method} {req.url[:100]}"))
    
    # Try to find search forms in the page by looking at data-role
    print("\n=== All listviews ===")
    for ul in soup.find_all("ul", {"data-role": "listview"}):
        divider = ul.find("li", {"data-role": "list-divider"})
        divider_text = divider.get_text(strip=True) if divider else "no divider"
        items = [li.get_text(strip=True)[:60] for li in ul.find_all("li", class_="ss-listview-internal")]
        print(f"  Divider: {divider_text}")
        for item in items[:3]:
            print(f"    {item}")
    
    browser.close()
