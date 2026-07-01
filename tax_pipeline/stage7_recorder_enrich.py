import pandas as pd
import time
import urllib.parse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import sys
import os

LIEN_TYPES = [
    "FEDERAL TAX LIEN",
    "STATE TAX LIEN",
    "ABSTRACT OF JUDGMENT",
    "MECHANIC'S LIEN",
    "MECHANICS LIEN",
    "NOTICE OF DELINQUENT ASSESSMENT",
    "NOTICE OF DEFAULT",
    "LIS PENDENS"
]

MORTGAGE_TYPES = [
    "DEED OF TRUST",
    "MORTGAGE"
]

DEED_TYPES = [
    "GRANT DEED",
    "QUITCLAIM DEED",
    "WARRANTY DEED",
    "CORPORATION GRANT DEED"
]

RECONVEYANCE_TYPES = [
    "RECONVEYANCE",
    "FULL RECONVEYANCE",
    "SUBSTITUTION OF TRUSTEE AND FULL RECONVEYANCE"
]

SATISFACTION_TYPES = [
    "SATISFACTION OF JUDGMENT",
    "RELEASE OF LIEN",
    "RELEASE OF FEDERAL TAX LIEN"
]

ASSIGNMENT_TYPES = [
    "ASSIGNMENT DEED OF TRUST",
    "ASSIGNMENT OF DEED OF TRUST",
    "ASSIGNMENT OF RENTS"
]

def format_name(name):
    """Parse an owner name string into {lastName, firstName} for EagleWeb search."""
    name = str(name).strip().upper()
    if not name or name in {"NAN", "NONE", "UNKNOWN", "UNKNOWN OWNER"}:
        return None

    markers = ["LLC", "INC", "CORP", "CORPORATION", "CO", "COMPANY", "TRUST", "TR", "REVOC", "ESTATE",
               "HOLDINGS", "PROPERTIES", "SERVICES", "ASSOCIATION", "REVOCABLE", "FAMILY"]
    is_entity = any(m in name.upper().split() for m in markers)

    if is_entity:
        return {"lastName": name.replace(",", " ").strip(), "firstName": ""}

    # Handle "LAST, FIRST MIDDLE" format (single comma = last,first)
    if name.count(",") == 1:
        parts = [p.strip() for p in name.split(",")]
        last = parts[0]
        first = parts[1].split()[0] if parts[1].split() else ""
        return {"lastName": last, "firstName": first}

    # No comma — assume "LAST FIRST" token order
    tokens = name.replace(",", " ").split()
    if len(tokens) >= 2:
        return {"lastName": tokens[0], "firstName": tokens[1]}
    return {"lastName": name, "firstName": ""}


def ensure_search_ready(page, state_file):
    """
    Handle all Tyler Tech EagleWeb wall states before issuing a search:
      1. Session keep-alive modal ("Do you need more time?") — button ID contains timestamp, so use text-based selector
      2. Disclaimer wall ("I Accept" button)
    Returns True if the search page is ready, False if we are stuck.
    """
    for attempt in range(3):
        try:
            # ── Priority 1: Session keep-alive modal ──────────────────────────
            # Button text is always "Yes - Continue" regardless of dynamic ID
            keepalive = page.locator("button:has-text('Yes - Continue'), button:has-text('Yes, Continue')")
            if keepalive.count() > 0 and keepalive.first.is_visible(timeout=1500):
                print("  [KEEPALIVE] Session timeout modal detected. Clicking 'Yes - Continue'...")
                keepalive.first.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(1)
                print("  [KEEPALIVE] Session extended.")
                continue  # Re-check after clicking

            # ── Priority 2: Disclaimer wall ──────────────────────────────────
            disclaimer = page.locator("#submitDisclaimerAccept")
            if disclaimer.count() > 0 and disclaimer.is_visible(timeout=1500):
                print("  [DISCLAIMER] Waiting for forced timer (up to 45s)...")
                start = time.time()
                accepted = False
                while time.time() - start < 45:
                    try:
                        disabled = page.eval_on_selector('#submitDisclaimerAccept', 'btn => btn.disabled')
                        if not disabled:
                            page.click('#submitDisclaimerAccept')
                            page.wait_for_load_state('networkidle')
                            # Save session after accepting disclaimer
                            try:
                                page.context.storage_state(path=state_file)
                            except Exception:
                                pass
                            print("  [DISCLAIMER] Accepted and session saved.")
                            accepted = True
                            break
                    except Exception:
                        pass
                    time.sleep(0.5)
                
                if not accepted:
                    print("  [DISCLAIMER] Timer never expired. Trying JS force-click...")
                    try:
                        page.evaluate("""
                            const btn = document.getElementById('submitDisclaimerAccept');
                            btn.disabled = false;
                            btn.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                        """)
                        page.wait_for_load_state('networkidle')
                        time.sleep(1)
                        try:
                            page.context.storage_state(path=state_file)
                        except Exception:
                            pass
                        print("  [DISCLAIMER] JS force-click executed and session saved.")
                    except Exception as e:
                        print(f"  [DISCLAIMER] JS force-click failed: {e}")
                        time.sleep(3)
                
                continue  # Re-check

            # ── Search page is ready ─────────────────────────────────────────
            # Verify the search field is visible
            search_field = page.locator("#field_BothNamesID")
            if search_field.count() > 0 and search_field.is_visible(timeout=3000):
                return True

            # Field not found — might be a different state; wait and retry
            time.sleep(2)

        except Exception as e:
            print(f"  [ensure_search_ready] attempt {attempt+1} error: {e}")
            time.sleep(2)

    print("  [ensure_search_ready] FAILED — page did not reach search state after 3 attempts.")
    return False

def scrape_liens(county="tehama"):
    print(f"[Stage 7] Starting Recorder Enrichment for {county.upper()} via Playwright...")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(base_dir, f"{county}_MASTER_leads.csv")
    output_file = os.path.join(base_dir, f"{county}_MASTER_leads_with_liens.csv")
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        sys.exit(1)
        
    df = pd.read_csv(input_file)
    
    if "active_liens" not in df.columns:
        df["active_liens"] = 0
    if "mortgages" not in df.columns:
        df["mortgages"] = 0
    if "has_assignment_of_rents" not in df.columns:
        df["has_assignment_of_rents"] = False
    if "has_affidavit_of_death" not in df.columns:
        df["has_affidavit_of_death"] = False
        
    with sync_playwright() as p:
        # Run in headless mode for background automation
        browser = p.chromium.launch(headless=True)
        
        state_file = os.path.join(base_dir, "eagleweb_state.json")
        
        if os.path.exists(state_file):
            context = browser.new_context(storage_state=state_file)
        else:
            context = browser.new_context()
            
        page = context.new_page()
        
        print("  Navigating to county portal...")
        page.add_init_script("""
            const _orig = window.setTimeout;
            window.setTimeout = function(fn, delay, ...args) {
                // Fire disclaimer timers instantly
                if (delay > 1000) delay = 100;
                return _orig(fn, delay, ...args);
            };
        """)
        recorder_urls = {
            "tehama": "https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1",
            "shasta": "https://eagleweb.co.shasta.ca.us/eaglesoftware/web/search/DOCSEARCH4S1"
        }
        url = recorder_urls.get(county, recorder_urls["tehama"])
        page.goto(url, timeout=60000)
        page.wait_for_load_state("load", timeout=60000)
        
        if "disclaimer" in page.url.lower() or "web" == page.url.rstrip("/").split("/")[-1]:
            print("  [ACTION] Disclaimer detected. Waiting for forced timer to complete...")
            try:
                page.wait_for_selector("#submitDisclaimerAccept:not([disabled])", timeout=20000)
                page.click("#submitDisclaimerAccept")
                page.wait_for_load_state("networkidle")
                time.sleep(1)
                context.storage_state(path=state_file)
                print("  [SUCCESS] Disclaimer accepted and session saved headlessly!")
            except Exception as e:
                print(f"  [WARNING] Initial disclaimer accept failed ({e}), loop will try again.")
                context.storage_state(path=state_file)
                print("  Session saved!")
            
        print("  Proceeding with automated searches...")
        
        # Run full-bore on the master dataset
        test_leads = df.copy()

        for idx, row in test_leads.iterrows():
            owner_name = str(row["assessee_name"])
            print(f"\n  [{idx}] Processing: {owner_name}")

            # ── Split multi-owner strings correctly ──────────────────────────
            # "LAST, FIRST" (one comma) = single person → pass as-is to format_name
            # "LAST FIRST, LAST FIRST" (two+ commas) = multiple owners → split on comma
            raw = owner_name.strip().upper()
            comma_count = raw.count(",")
            if comma_count == 0:
                owners = [raw]                                   # "SOTO DANIEL"
            elif comma_count == 1:
                owners = [raw]                                   # "SOTO, DANIEL" → format_name handles it
            else:
                # Heuristic: token pairs separated by commas, e.g. "SOTO JOSE, SMITH MARY"
                owners = [o.strip() for o in raw.split(",") if o.strip()]

            seen_doc_numbers = set()
            seen_lien_texts = set()
            seen_satisfaction_texts = set()
            raw_liens = 0
            raw_satisfactions = 0
            raw_mortgages = 0
            raw_reconveyances = 0
            has_assignment_of_rents = False
            has_affidavit_of_death = False
            ownership_status = "Current"

            for o_name in owners:
                parsed = format_name(o_name)
                if not parsed:
                    continue

                print(f"    -> Searching: '{parsed['lastName']}' / '{parsed['firstName']}' ...", end=" ")

                # ── Navigate to search page with session wall handling ────────
                for attempt in range(3):
                    try:
                        page.goto("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1", timeout=30000)
                        page.wait_for_load_state("networkidle", timeout=30000)
                        break
                    except Exception as nav_err:
                        if attempt == 2:
                            print(f"Navigation failed: {nav_err}")
                        time.sleep(3)

                # ── Handle disclaimer / session keep-alive BEFORE searching ──
                ready = ensure_search_ready(page, state_file)
                if not ready:
                    print(f"SKIP — page not ready.")
                    continue

                try:
                    # Clear previous search if the button exists
                    try:
                        clear_btn = page.locator("#clearSearchButton")
                        if clear_btn.count() > 0 and clear_btn.is_visible(timeout=2000):
                            clear_btn.click()
                            time.sleep(0.5)
                    except Exception:
                        pass

                    # Fill search field
                    search_str = f"{parsed['lastName']} {parsed['firstName']}".strip()
                    page.fill("#field_BothNamesID", search_str, timeout=8000)
                    time.sleep(0.5)

                    # Click search (it's an <a> element with id=searchButton)
                    page.click("#searchButton")

                    # Wait for results to load (either docs or "no results" state)
                    time.sleep(4)
                    try:
                        page.wait_for_selector(".ui-li-static", timeout=8000)
                    except Exception:
                        pass  # 0 results is fine

                    # After results load, check AGAIN for session modal that may have fired
                    ensure_search_ready(page, state_file)
                    
                    soup = BeautifulSoup(page.content(), "html.parser")
                    results = soup.find_all("li", class_="ui-li-static")
                    
                    found = 0
                    for li in results:
                        doc_text = li.text.strip().upper()
                        
                        # Skip bulk/mass subdivision HOA documents (affects 400+ owners at once)
                        import re
                        if "NOTICE OF ASSESSMENT LIEN" in doc_text:
                            if re.search(r'GRANTOR\s*\(\d{2,}\)', doc_text):
                                continue


                        # Deduplicate using the raw text block, which contains the doc number
                        import re
                        doc_num_match = re.search(r'(\d{10})', doc_text)
                        doc_num = doc_num_match.group(1) if doc_num_match else doc_text[:20]
                        
                        is_new_doc = doc_num not in seen_doc_numbers
                        
                        if any(l in doc_text for l in LIEN_TYPES):
                            if doc_text not in seen_lien_texts:
                                seen_lien_texts.add(doc_text)
                                raw_liens += 1
                                found += 1
                        if any(s in doc_text for s in SATISFACTION_TYPES):
                            if doc_text not in seen_satisfaction_texts:
                                seen_satisfaction_texts.add(doc_text)
                                raw_satisfactions += 1
                                found += 1
                                
                        is_assignment = any(a in doc_text for a in ASSIGNMENT_TYPES)
                        if is_assignment:
                            has_assignment_of_rents = True
                            
                        if "AFFIDAVIT OF DEATH" in doc_text:
                            has_affidavit_of_death = True
                            
                        if not is_assignment and is_new_doc:
                            seen_doc_numbers.add(doc_num)
                            if any(m in doc_text for m in MORTGAGE_TYPES):
                                raw_mortgages += 1
                                found += 1
                            if any(r in doc_text for r in RECONVEYANCE_TYPES):
                                raw_reconveyances += 1
                                found += 1
                            
                        if any(d in doc_text for d in DEED_TYPES):
                            # It's a deed. We check if the target owner is the Grantor.
                            if "GRANTOR:" in doc_text:
                                grantor_section = doc_text.split("GRANTOR:")[1].split("GRANTEE:")[0]
                                if parsed['lastName'] in grantor_section:
                                    if "GRANTEE:" in doc_text:
                                        grantee_section = doc_text.split("GRANTEE:")[1]
                                        
                                        is_possible_transfer = False
                                        if parsed['lastName'] in grantee_section:
                                            is_possible_transfer = True
                                        elif any(entity_word in grantee_section for entity_word in ["TRUST", "LLC", "INC", "CORP", "FAMILY", "REVOCABLE"]):
                                            if parsed['firstName'] and parsed['firstName'] in grantee_section:
                                                is_possible_transfer = True
                                        
                                        if is_possible_transfer:
                                            ownership_status = "Possible Transfer"
                                        else:
                                            ownership_status = "Sold / Transfer Detected"
                                    else:
                                        ownership_status = "Sold / Transfer Detected"
                            
                    print(f"found {found} new relevant docs.")
                except Exception as e:
                    print(f"FAILED ({type(e).__name__}: {e})")
                    # Save DOM snapshot for debugging
                    try:
                        debug_path = os.path.join(base_dir, "debug_dom.html")
                        with open(debug_path, "w", encoding="utf-8") as dbf:
                            dbf.write(page.content())
                        print(f"      [DEBUG] DOM snapshot saved to {debug_path}")
                    except Exception:
                        pass
                    
            # Net open counts (floor at 0):
            df.at[idx, "active_liens"] = max(0, raw_liens - raw_satisfactions)
            df.at[idx, "mortgages"] = max(0, raw_mortgages - raw_reconveyances)
            df.at[idx, "ownership_status"] = ownership_status
            df.at[idx, "has_assignment_of_rents"] = has_assignment_of_rents
            df.at[idx, "has_affidavit_of_death"] = has_affidavit_of_death
            
            # Incremental save per row to prevent data loss on crash
            df.to_csv(output_file, index=False)
                
        browser.close()
        
    df.to_csv(output_file, index=False)
    print(f"\n[Stage 7] Enrichment Complete. Saved to {output_file}")

if __name__ == "__main__":
    county_arg = sys.argv[1] if len(sys.argv) > 1 else "tehama"
    scrape_liens(county_arg)
