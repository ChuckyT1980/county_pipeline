#!/usr/bin/env python3
import sys
import json
import time
import requests
import pandas as pd
from datetime import datetime

COUNTY = "tehama"
HOST = "https://common1.mptsweb.com"
TAX_YEAR = "2025"

def get_parcels(session, prefix6):
    url = f"{HOST}/MBC/api/search/{COUNTY}/0000-CURR/feeparcel/{prefix6}"
    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        if isinstance(data, str):
            data = json.loads(data)
        rows = data.get("Table", {}).get("Row", [])
        if isinstance(rows, dict):
            rows = [rows]
        return rows
    except Exception as e:
        print(f"  error for {prefix6}: {e}")
        return []

def norm_apn(asmt):
    ac = str(asmt).replace("-", "").strip().zfill(12)
    return f"{ac[0:3]}-{ac[3:6]}-{ac[6:9]}-{ac[9:12]}"

def main():
    book = int(sys.argv[1]) if len(sys.argv) > 1 else 64
    out_csv = f"tehama_test_book{book:03d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    })
    search_url = f"{HOST}/MBC/{COUNTY}/tax/search"
    session.get(search_url, timeout=15)
    session.headers["Referer"] = search_url
    time.sleep(1)
    records = []
    seen = set()
    print(f"Testing Tehama discovery for book {book:03d} ...")
    for page in range(0, 1000, 10):
        prefix6 = f"{book:03d}{page:03d}"
        rows = get_parcels(session, prefix6)
        for r in rows:
            asmt = r.get("Asmt")
            if asmt and asmt not in seen:
                seen.add(asmt)
                records.append({
                    "asmt": norm_apn(asmt),
                    "asmt_raw": str(asmt).replace("-", "").strip().zfill(12),
                    "address": r.get("Situs1", ""),
                    "fee_parcel": r.get("FeeParcel", ""),
                    "roll_cat": r.get("RollCategory", ""),
                    "detail_url": f"{HOST}/MBC/{COUNTY}/tax/main/{str(asmt).replace('-', '')}/{TAX_YEAR}/0000",
                })
        if rows:
            print(f"  {prefix6}: +{len(rows)} rows (total: {len(records)})")
        time.sleep(0.02)
    df = pd.DataFrame(records)
    df.to_csv(out_csv, index=False)
    print(f"\nDone. Found {len(records)} parcels in book {book:03d}.")
    print(f"Output: {out_csv}")

if __name__ == "__main__":
    main()
