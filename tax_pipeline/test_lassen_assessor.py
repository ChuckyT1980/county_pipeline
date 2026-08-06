"""
Quick Lassen assessor smoke test.
Verifies MPTS discovery API and tax detail pages work for Lassen.
Run: python test_lassen_assessor.py
"""
import requests
import time
import re
from bs4 import BeautifulSoup

COUNTY = "lassen"
HOST = "https://common1.mptsweb.com"
API_BASE = f"{HOST}/MBC/api/search/{COUNTY}/0000-CURR/feeparcel/"
TAX_YEAR = "2025"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
})

# Warm up session
search_url = f"{HOST}/MBC/{COUNTY}/tax/search"
session.get(search_url, timeout=15)
session.headers["Referer"] = search_url
time.sleep(1)

print(f"[{COUNTY.upper()}] Probing discovery API...")

# Try a few prefixes that should return parcels
probes = ["001050", "005050", "010050", "050050", "100050"]
found = 0
sample_apn = None
for prefix in probes:
    try:
        r = session.get(API_BASE + prefix, timeout=10)
        print(f"  {prefix}: status={r.status_code}", end=" ")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, str):
                import json
                data = json.loads(data)
            rows = data.get("Table", {}).get("Row", [])
            if rows and isinstance(rows, list) and len(rows) > 0:
                found += 1
                print(f"rows={len(rows)} first={rows[0].get('Asmt')}")
                if sample_apn is None:
                    sample_apn = str(rows[0].get("Asmt")).replace("-", "").zfill(12)
            else:
                print("rows=0")
        else:
            print(f"body={r.text[:80]}")
    except Exception as e:
        print(f"ERROR: {e}")
    time.sleep(0.2)

if not sample_apn:
    print("\nNo parcels found in probe. Lassen MPTS discovery may be unavailable or require different prefixes.")
    raise SystemExit(1)

print(f"\n[{COUNTY.upper()}] Found parcels in {found}/{len(probes)} probes.")
print(f"[{COUNTY.upper()}] Sample APN: {sample_apn}")

# Test tax detail page
print(f"\n[{COUNTY.upper()}] Testing tax detail page...")
tax_url = f"{HOST}/MBC/{COUNTY}/tax/main/{sample_apn}/{TAX_YEAR}/0000"
try:
    r = session.get(tax_url, timeout=15)
    print(f"  status={r.status_code}")
    if r.status_code == 200:
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text("\n")
        # Look for balance/status signals
        has_totals = "Totals" in text or "Total Balance" in text
        has_installment = "Installment" in text
        print(f"  has_totals={has_totals}, has_installment={has_installment}")
except Exception as e:
    print(f"  ERROR: {e}")

# Test MBAP AsrPrint
print(f"\n[{COUNTY.upper()}] Testing MBAP AsrPrint...")
asr_url = f"{HOST}/mbap/{COUNTY}/asr/AsrPrint/{sample_apn}"
try:
    r = session.get(asr_url, timeout=15)
    print(f"  status={r.status_code}")
    if r.status_code == 200:
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text("\n")
        # Look for owner name
        has_owner = any(x in text for x in ["Assessee Name", "Owner", "Owner Name"])
        print(f"  has_owner_field={has_owner}")
except Exception as e:
    print(f"  ERROR: {e}")

print(f"\n[{COUNTY.upper()}] Smoke test complete.")
