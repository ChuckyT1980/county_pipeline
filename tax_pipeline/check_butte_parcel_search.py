from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    # Check PARCELSEARCH endpoints for APN fields
    for action in [
        "/web/search/PARCELSEARCH481S1",
        "/web/search/PARCELSEARCH482S1",
        "/web/search/PARTYSEARCH481S1",
        "/web/search/DOCSEARCH481S2",
    ]:
        url = f"https://recorder.buttecounty.net{action}"
        print(f"\n=== {action} ===")
        try:
            page.goto(url, timeout=15000)
            page.wait_for_load_state("networkidle", timeout=10000)
            time.sleep(1)
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(page.content(), "html.parser")
            
            # Find form fields
            for inp in soup.find_all("input"):
                name = inp.get("name", "")
                fid = inp.get("id", "")
                itype = inp.get("type", "")
                placeholder = inp.get("placeholder", "")
                label = ""
                # Find corresponding label
                if fid:
                    lbl = soup.find("label", {"for": fid})
                    if lbl:
                        label = lbl.get_text(strip=True)
                
                if name and itype not in ("hidden", "checkbox") and name != "field_UseAdvancedSearch":
                    print(f"  [{itype:8s}] name={name:45s} label={label:30s} placeholder={placeholder}")
            
            # Also dump all labels
            for lbl in soup.find_all("label"):
                for_val = lbl.get("for", "")
                text = lbl.get_text(strip=True)
                if for_val and text and "UseAdvanced" not in for_val:
                    print(f"  LABEL: {for_val:45s} -> {text}")
                    
        except Exception as e:
            print(f"  ERROR: {e}")
    
    browser.close()
