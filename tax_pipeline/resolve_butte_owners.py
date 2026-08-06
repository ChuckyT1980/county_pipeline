#!/usr/bin/env python3
"""
Butte Owner Name Resolver — Stage 4.5

Strategy:
  1. Fetch AsrPrint from common1.mptsweb.com to get doc_number
  2. Convert doc_number to Tyler format: YYYY-NNNNNNN
  3. Search Butte Tyler recorder (DOCSEARCH481S2) by document number
  4. Extract Grantee name = current owner
  5. Update MASTER CSV with owner_name

Usage: python resolve_butte_owners.py
"""
import csv, time, re, os, sys
import requests
import concurrent.futures
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(BASE, "..", "archive")
MASTER_CSV = os.path.join(ARCHIVE, "butte_MASTER_leads_with_liens.csv")
OUTPUT_CSV = os.path.join(BASE, "butte_MASTER_leads_with_liens.csv")

def get_doc_numbers():
    """Batch-fetch doc_numbers from AsrPrint for all APNs. Returns dict {apn: doc_number}."""
    raw_apns = []
    with open(MASTER_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_apns.append(row["asmt"].strip())

    apns = [a.zfill(12) for a in raw_apns]

    def fetch(apn):
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://common1.mptsweb.com/mbap/butte/asr",
        })
        try:
            r = s.get(f"https://common1.mptsweb.com/mbap/butte/asr/AsrPrint/{apn}", timeout=15)
            if r.status_code != 200:
                return (apn, None)
            soup = BeautifulSoup(r.text, "html.parser")
            for row in soup.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if "Current Document Number" in label and value:
                        return (apn, value.strip())
            return (apn, None)
        except:
            return (apn, None)

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        fut = {ex.submit(fetch, apn): apn for apn in apns}
        for f in concurrent.futures.as_completed(fut):
            apn, doc = f.result()
            results[apn] = doc

    return results

def recorder_format(doc_number):
    """Convert 2024R0030607 -> 2024-0030607"""
    if not doc_number or len(doc_number) < 6:
        return None
    return doc_number[:4] + "-" + doc_number[5:]

def resolve_owners_via_recorder(doc_map):
    """
    Use Playwright to search Butte Tyler recorder by document number.
    Returns dict {apn: owner_name} for successful lookups.
    """
    print(f"\nResolving {len(doc_map)} document numbers via Butte recorder...")
    
    owner_map = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Handle disclaimer
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
        found = 0
        no_result = 0
        error = 0

        for i, (apn, doc_num) in enumerate(doc_map.items()):
            rec_fmt = recorder_format(doc_num)
            if not rec_fmt:
                continue

            try:
                doc_field.fill(rec_fmt, timeout=5000)
                time.sleep(0.3)
                search_btn.click()
                time.sleep(3)
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(1)

                soup = BeautifulSoup(page.content(), "html.parser")
                full_text = soup.get_text()

                if "No results found" in full_text:
                    no_result += 1
                    if (i+1) % 25 == 0:
                        print(f"  Progress: {i+1}/{len(doc_map)} (found: {found}, none: {no_result}, err: {error})")
                    continue

                # Extract Grantee name — look for "Grantee" section in the page
                grantee = None
                lines = full_text.split("\n")
                for i, line in enumerate(lines):
                    clean = line.strip()
                    if "Grantee" in clean and len(clean) < 30:
                        # Look ahead for the name (skip "Clear text", "1", etc.)
                        for j in range(i+1, min(i+8, len(lines))):
                            c = lines[j].strip()
                            if c and c not in ("Clear text", "1") and not any(x in c for x in ["Grantor", "Recording", "Document", "Recent", "Cart", "Filter", "Apply", "Print", "Showing", "Sort", "(", "["]):
                                if len(c) > 2 and len(c) < 120:
                                    grantee = c
                                break
                        break

                if grantee:
                    owner_map[apn] = grantee
                    found += 1
                else:
                    no_result += 1

            except Exception as e:
                error += 1

            if (i+1) % 25 == 0:
                print(f"  Progress: {i+1}/{len(doc_map)} (found: {found}, none: {no_result}, err: {error})")

        browser.close()

    print(f"\nRecorder search complete: {found} owners found, {no_result} no results, {error} errors")
    return owner_map

def update_csv(owner_map):
    """Update MASTER CSV with resolved owner names."""
    with open(MASTER_CSV) as f:
        rows = list(csv.DictReader(f))
    
    updated = 0
    fields = list(rows[0].keys())
    for col in ("owner_name", "assessee_name"):
        if col not in fields:
            fields.append(col)

    for row in rows:
        raw_apn = row["asmt"].strip()
        padded = raw_apn.zfill(12)
        if padded in owner_map:
            name = owner_map[padded]
            row["owner_name"] = name
            row["assessee_name"] = name
            row["owner_source"] = "RECORDER_DOC_SEARCH"
            updated += 1

    with open(OUTPUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"\nUpdated {updated} owner names in {OUTPUT_CSV}")

if __name__ == "__main__":
    print("=" * 60)
    print("BUTTE OWNER RESOLVER — Stage 4.5")
    print("=" * 60)

    # Step 1: Get all doc_numbers from AsrPrint
    print("\n[Step 1] Fetching doc_numbers from AsrPrint...")
    doc_map = get_doc_numbers()
    valid = {k: v for k, v in doc_map.items() if v}
    print(f"  {len(valid)}/{len(doc_map)} have document numbers")

    if len(valid) < 10:
        print("  Too few doc numbers, exiting.")
        sys.exit(1)

    # Step 2: Search recorder by doc_number
    print("\n[Step 2] Searching Butte recorder by document number...")
    owner_map = resolve_owners_via_recorder(valid)

    # Step 3: Update CSV
    print("\n[Step 3] Updating MASTER CSV...")
    update_csv(owner_map)

    print("\nDone! Next: run Stage 7 recorder enrich for liens/mortgages:")
    print("  python -m tax_pipeline.stage7_recorder_enrich butte")
