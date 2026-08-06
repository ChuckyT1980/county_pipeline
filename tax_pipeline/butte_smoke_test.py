"""
Butte Recorder Smoke Test — tests the fixed timing flow on 3 Butte parcels.
Run: python butte_smoke_test.py
"""
import json, time, sys
sys.path.insert(0, "..")

from playwright.sync_api import sync_playwright
from tax_pipeline.recorder_config import RECORDER_CONFIG

TEST_DOCS = [
    ("2024-0030607", "butte_2271003000"),   # Delinquent, has doc number
    ("2024-0016848", "butte_2292001000"),   # Delinquent, has doc number
    ("2020-0035761", "butte_shasta_ref"),   # From Shasta reference (doc format test)
]

def smoke_test():
    cfg = RECORDER_CONFIG["butte"]
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = ctx.new_page()
        page.set_default_timeout(15000)

        # ── Accept disclaimer ──
        print("Loading Butte name search page...")
        page.goto(cfg["name_search_url"], wait_until="networkidle")
        page.wait_for_timeout(2000)

        disclaimer_sel = cfg["disclaimer_selector"]
        if page.query_selector(disclaimer_sel):
            print("Accepting disclaimer...")
            page.click(disclaimer_sel, force=True)
            page.wait_for_timeout(3000)
            page.wait_for_load_state("networkidle")
            if "search" not in page.url.lower():
                page.goto(cfg["name_search_url"], wait_until="networkidle")
                page.wait_for_timeout(2000)

        # ── Test each doc number ──
        for doc_fmt, label in TEST_DOCS:
            print(f"\n--- Testing {label} (doc: {doc_fmt}) ---")

            # Pivot 1: Document search
            page.goto(cfg["doc_search_url"], wait_until="networkidle")
            page.wait_for_timeout(2000)

            # Handle disclaimer if it reappears
            if page.query_selector(disclaimer_sel):
                page.click(disclaimer_sel, force=True)
                page.wait_for_timeout(2000)
                page.wait_for_load_state("networkidle")
                if "DOCSEARCH" not in page.url:
                    page.goto(cfg["doc_search_url"], wait_until="networkidle")
                    page.wait_for_timeout(2000)

            # Wait for the field
            try:
                page.wait_for_selector(cfg["doc_search_field"], timeout=10000)
                print(f"  [OK] Found {cfg['doc_search_field']}")
            except Exception as e:
                print(f"  [FAIL] {cfg['doc_search_field']} NOT FOUND: {e}")
                continue

            page.fill(cfg["doc_search_field"], doc_fmt)
            page.click(cfg["search_button"])

            try:
                page.wait_for_url("**/web/searchResults/**", timeout=10000)
            except:
                pass

            page.wait_for_timeout(3000)
            elements = page.query_selector_all(cfg["results_selector"])

            if not elements:
                print(f"  [FAIL] No results found for {doc_fmt}")
                continue

            print(f"  [OK] Found {len(elements)} result(s)")

            # Parse first result
            text = elements[0].inner_text()
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            primary_name = None
            for j, ln in enumerate(lines):
                if "Grantee" in ln and j + 1 < len(lines):
                    primary_name = lines[j+1]
                    break
                elif "Grantor" in ln and j + 1 < len(lines) and not primary_name:
                    primary_name = lines[j+1]

            if primary_name:
                print(f"  [OK] Grantee: {primary_name}")

                # Pivot 2: Name search for encumbrance chain
                page.goto(cfg["name_search_url"], wait_until="networkidle")
                page.wait_for_timeout(2000)

                try:
                    page.wait_for_selector(cfg["search_field"], timeout=10000)
                    print(f"  [OK] Found {cfg['search_field']}")
                except Exception as e:
                    print(f"  [FAIL] {cfg['search_field']} NOT FOUND: {e}")
                    continue

                page.fill(cfg["search_field"], primary_name)
                page.click(cfg["search_button"])

                try:
                    page.wait_for_url("**/web/searchResults/**", timeout=15000)
                except:
                    pass

                page.wait_for_timeout(3000)
                name_elements = page.query_selector_all(cfg["results_selector"])
                chain_count = len(name_elements) if name_elements else 0
                print(f"  [OK] Name search returned {chain_count} record(s)")

                results.append({
                    "label": label,
                    "doc": doc_fmt,
                    "grantee": primary_name,
                    "chain_records": chain_count,
                    "status": "PASS"
                })
            else:
                print(f"  [FAIL] Could not extract Grantee from results")
                results.append({"label": label, "status": "NO_GRANTEE"})

        browser.close()

    print("\n" + "="*60)
    print("SMOKE TEST RESULTS")
    print("="*60)
    for r in results:
        status = r["status"]
        name = r.get("grantee", "?")
        chain = r.get("chain_records", 0)
        print(f"  {r['label']:30s} | {status:12s} | {name:30s} | chain={chain}")

    passed = sum(1 for r in results if r["status"] == "PASS")
    print(f"\n  {passed}/{len(results)} passed")
    return passed == len(results)

if __name__ == "__main__":
    ok = smoke_test()
    sys.exit(0 if ok else 1)
