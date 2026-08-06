#!/usr/bin/env python3
"""Small Shasta end-to-end sample: 3 books, 10 pages per book."""
import json, time, requests, pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime

COUNTY = "shasta"
HOST = "https://common2.mptsweb.com"
BOOKS = [35]
PAGES = range(0, 100, 10)  # 10 pages per book
TAX_YEAR = "2025"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json,text/javascript,*/*",
})

# Stage 1: Discovery
parcels = []
for book in BOOKS:
    for page in PAGES:
        prefix = f"{book:03d}{page:03d}"
        url = f"{HOST}/MBC/api/search/{COUNTY}/0000-CURR/feeparcel/{prefix}"
        try:
            r = session.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, str):
                    data = json.loads(data)
                rows = data.get("Table", {}).get("Row", [])
                if isinstance(rows, dict):
                    rows = [rows]
                for row in rows:
                    asmt = str(row.get("Asmt", "")).replace("-", "").zfill(12)
                    if asmt:
                        parcels.append({
                            "asmt": asmt,
                            "address": row.get("Situs1", ""),
                            "fee_parcel": str(row.get("FeeParcel", "")).replace("-", "").zfill(12),
                            "roll_cat": row.get("RollCategory", "CS"),
                            "tra": row.get("Tra", ""),
                            "county": COUNTY,
                            "year": TAX_YEAR,
                        })
        except Exception as e:
            print(f"Error {prefix}: {e}")
        time.sleep(0.02)
    print(f"Book {book:03d}: {len(parcels)} parcels total")

# Deduplicate
seen = set()
parcels = [p for p in parcels if not (p["asmt"] in seen or seen.add(p["asmt"]))]
print(f"\nDiscovered {len(parcels)} unique parcels")

if not parcels:
    print("No parcels found. Aborting.")
    exit(1)

# Stage 2: Verify tax details
print("\nVerifying tax details...")
verified = []
for p in parcels[:30]:
    url = f"{HOST}/MBC/{COUNTY}/tax/main/{p['asmt']}/{TAX_YEAR}/0000"
    try:
        r = session.get(url, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text("\n")
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            def val_after(kw, lines):
                for i, ln in enumerate(lines):
                    if kw.lower() in ln.lower():
                        for j in range(i+1, min(i+5, len(lines))):
                            if lines[j].lower() != kw.lower():
                                return lines[j]
                return None
            it = next((i for i, l in enumerate(lines) if "totals" in l.lower()), None)
            balance = None
            if it:
                balance = val_after("Total Balance", lines[it:it+20]) or val_after("Balance", lines[it:it+20])
            p["v_total_balance"] = balance
            p["v_delinquent"] = any("LATE" in str(val_after("Paid Status", lines[i:i+15])).upper() for i in range(len(lines)))
            p["verified_url"] = url
            verified.append(p)
    except Exception as e:
        print(f"Verify error {p['asmt']}: {e}")
    time.sleep(0.1)

print(f"Verified {len(verified)} parcels")

# Save discovery/verification CSV
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
disc_csv = f"shasta_sample_discovery_{ts}.csv"
pd.DataFrame(verified).to_csv(disc_csv, index=False)
print(f"Saved: {disc_csv}")

# Now run stage2_verify, stage4, stage7 on this sample
print("\nNext steps — run these commands:")
print(f"  python stage2_verify.py {COUNTY} {disc_csv}")
print(f"  python stage4_owner_enrich.py shasta_crm_*.csv")
print(f"  python -m tax_pipeline.stage7_recorder_enrich {COUNTY}")
