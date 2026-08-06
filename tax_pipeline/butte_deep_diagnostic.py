"""
Deep diagnostic: dump raw HTML of Butte search results to understand
exact structure, test doc type extraction, and test name search formats.
"""
import sys, re
sys.path.insert(0, "..")
from playwright.sync_api import sync_playwright
from tax_pipeline.recorder_config import RECORDER_CONFIG

cfg = RECORDER_CONFIG["butte"]
disclaimer_sel = cfg["disclaimer_selector"]

def accept_disclaimer(page):
    if page.query_selector(disclaimer_sel):
        page.click(disclaimer_sel, force=True)
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_default_timeout(15000)

    # ── PART A: Doc search — dump raw HTML structure ──
    print("=" * 60)
    print("PART A: Doc Search — Raw HTML Inspection")
    print("=" * 60)

    page.goto(cfg["doc_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    accept_disclaimer(page)
    if "DOCSEARCH" not in page.url:
        page.goto(cfg["doc_search_url"], wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

    page.wait_for_selector(cfg["doc_search_field"], timeout=10000)
    page.fill(cfg["doc_search_field"], "2024-0030607")
    page.click(cfg["search_button"])

    try:
        page.wait_for_url("**/web/searchResults/**", timeout=15000)
    except:
        pass
    page.wait_for_timeout(3000)
    page.wait_for_load_state("networkidle")

    # Dump inner HTML of first result
    rows = page.query_selector_all(cfg["results_selector"])
    print(f"Results found: {len(rows)}")
    if rows:
        # Get raw HTML
        html = rows[0].evaluate("el => el.outerHTML")
        print("\n--- Raw HTML of first result (first 3000 chars) ---")
        print(html[:3000])

        # Get inner_text
        text = rows[0].inner_text()
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        print("\n--- inner_text lines ---")
        for idx, ln in enumerate(lines):
            print(f"  [{idx}] = '{ln}'")

        # Test doc type extraction approaches
        print("\n--- Doc type extraction test ---")
        for idx, ln in enumerate(lines):
            if re.search(r'\d{4}-\d{7}', ln):
                print(f"  Doc line at index [{idx}]: '{ln}'")
                # Try various separators
                for sep in ["\u00a0\u25a0\u00a0", "\u00a0", " — ", " ■ ", "■"]:
                    if sep in ln:
                        parts = ln.split(sep)
                        print(f"    Separator '{repr(sep)}' splits to: {parts}")
                        break
                else:
                    print(f"    No known separator found. Trying regex...")
                    m = re.search(r'(\d{4}-\d{7})\s*(.*)', ln)
                    if m:
                        print(f"    Regex: doc_number={m.group(1)}, doc_type='{m.group(2).strip()}'")

    # ── PART B: Name search — test various formats ──
    print("\n" + "=" * 60)
    print("PART B: Name Search — Format Tests")
    print("=" * 60)

    # Extract grantee from Part A
    grantee = None
    if rows:
        text = rows[0].inner_text()
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        for j, ln in enumerate(lines):
            if "Grantee" in ln and j + 1 < len(lines):
                grantee = lines[j+1]
                break
    print(f"Grantee from doc search: {grantee}")

    if grantee:
        # Try different name formats
        parts = grantee.split()
        formats_to_try = [
            grantee,                          # "HANSON ALEXANDER RAEL"
            " ".join(parts[:2]),              # "HANSON ALEXANDER" (last first)
            parts[0],                         # "HANSON" (last name only)
            f"{parts[0]} {parts[-1]}",        # "HANSON RAEL" (last + middle)
        ]

        for fmt in formats_to_try:
            print(f"\n--- Searching: '{fmt}' ---")
            page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)
            accept_disclaimer(page)
            if "DOCSEARCH" not in page.url:
                page.goto(cfg["name_search_url"], wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(2000)

            page.wait_for_selector(cfg["search_field"], timeout=10000)
            page.fill(cfg["search_field"], fmt)
            page.click(cfg["search_button"])

            try:
                page.wait_for_url("**/web/searchResults/**", timeout=15000)
            except:
                pass
            page.wait_for_timeout(3000)
            page.wait_for_load_state("networkidle")

            name_rows = page.query_selector_all(cfg["results_selector"])
            print(f"  Results: {len(name_rows)}")
            for nr in name_rows[:3]:
                t = nr.inner_text()
                ls = [l.strip() for l in t.split("\n") if l.strip()]
                print(f"    > {ls[0] if ls else '?'}")

    # ── PART C: Test #searchButton ambiguity ──
    print("\n" + "=" * 60)
    print("PART C: #searchButton selector check")
    print("=" * 60)

    page.goto(cfg["doc_search_url"], wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    accept_disclaimer(page)
    if "DOCSEARCH" not in page.url:
        page.goto(cfg["doc_search_url"], wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

    page.wait_for_selector(cfg["doc_search_field"], timeout=10000)

    all_buttons = page.query_selector_all("#searchButton")
    print(f"Elements matching '#searchButton': {len(all_buttons)}")
    for b in all_buttons:
        tag = b.evaluate("el => el.tagName")
        text = b.inner_text()
        visible = b.is_visible()
        print(f"  <{tag}> text='{text}' visible={visible}")

    browser.close()
    print("\nDONE")
