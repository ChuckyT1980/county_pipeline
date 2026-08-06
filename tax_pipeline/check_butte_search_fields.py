from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    def handle_disclaimer(url):
        page.goto(url, timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(1)
        disclaimer = page.locator("#submitDisclaimerAccept")
        if disclaimer.count() > 0 and disclaimer.is_visible(timeout=2000):
            try:
                disabled = page.eval_on_selector("#submitDisclaimerAccept", "btn => btn.disabled")
                if not disabled:
                    disclaimer.click()
                    time.sleep(2)
                    page.wait_for_load_state("networkidle", timeout=15000)
                else:
                    # Wait for it to become enabled
                    for _ in range(20):
                        time.sleep(0.5)
                        disabled = page.eval_on_selector("#submitDisclaimerAccept", "btn => btn.disabled")
                        if not disabled:
                            disclaimer.click()
                            time.sleep(2)
                            break
            except:
                pass
    
    for label, action in [
        ("Parcel Search 481", "/web/search/PARCELSEARCH481S1"),
        ("Party Search 481", "/web/search/PARTYSEARCH481S1"),
        ("Doc Number Search 481", "/web/search/DOCSEARCH481S2"),
        ("Advanced Search 481", "/web/search/DOCSEARCH481S6"),
    ]:
        url = f"https://recorder.buttecounty.net{action}"
        print(f"\n=== {label}: {action} ===")
        try:
            handle_disclaimer(url)
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(page.content(), "html.parser")
            
            fields = []
            for inp in soup.find_all("input"):
                name = inp.get("name", "")
                fid = inp.get("id", "")
                itype = inp.get("type", "")
                placeholder = inp.get("placeholder", "")
                label_text = ""
                if fid:
                    lbl = soup.find("label", {"for": fid})
                    if lbl:
                        label_text = lbl.get_text(strip=True)
                if name and itype not in ("hidden", "checkbox", "radio"):
                    fields.append((itype, name, label_text, placeholder))
                    print(f"  [{itype:8s}] {name:45s} label='{label_text[:40]:40s}' placeholder='{placeholder}'")
            
            # Also check for select dropdowns
            for sel in soup.find_all("select"):
                name = sel.get("name", "")
                fid = sel.get("id", "")
                label_text = ""
                if fid:
                    lbl = soup.find("label", {"for": fid})
                    if lbl:
                        label_text = lbl.get_text(strip=True)
                options = [(o.get("value",""), o.get_text(strip=True)) for o in sel.find_all("option") if o.get("value","")]
                print(f"  [SELECT ] {name:45s} label='{label_text:40s}' options={options[:5]}")
            
            if not fields:
                print(f"  (no form fields found)")
                
        except Exception as e:
            print(f"  ERROR: {e}")
    
    browser.close()
