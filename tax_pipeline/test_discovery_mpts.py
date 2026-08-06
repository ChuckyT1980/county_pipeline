#!/usr/bin/env python3
import sys
import json
import time
import requests
import pandas as pd
from datetime import datetime
from tax_pipeline.config import COUNTY_CONFIG


def get_parcels(session, cfg, prefix6):
    county = cfg["county_slug"]
    url = f"{cfg['host']}/MBC/api/search/{county}/0000-CURR/feeparcel/{prefix6}"
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
    county = sys.argv[1].lower() if len(sys.argv) > 1 else "tehama"
    book = int(sys.argv[2]) if len(sys.argv) > 2 else 64

    if county not in COUNTY_CONFIG:
        print(f"Unknown county: {county}")
        print(f"Known: {', '.join(COUNTY_CONFIG.keys())}")
        sys.exit(1)

    cfg = COUNTY_CONFIG[county]
    out_csv = f"{county}_test_book{book:03d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    session = requests.Session()
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    retry_strategy = Retry(
        total=10, 
        backoff_factor=2, 
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    })

    search_url = f"{cfg['host']}/MBC/{county}/tax/search"
    session.get(search_url, timeout=15)
    session.headers["Referer"] = search_url
    time.sleep(1)

    records = []
    seen = set()
    tax_year = cfg["tax_year"]

    print(f"Testing {county.upper()} discovery for book {book:03d} ...")
    for page in range(0, 1000, 10):
        prefix6 = f"{book:03d}{page:03d}"
        rows = get_parcels(session, cfg, prefix6)
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
                    "detail_url": f"{cfg['host']}/MBC/{county}/tax/main/{str(asmt).replace('-', '')}/{tax_year}/0000",
                    "county": county,
                })
        if rows:
            print(f"  {prefix6}: +{len(rows)} rows (total: {len(records)})")
        time.sleep(0.02)

    pd.DataFrame(records).to_csv(out_csv, index=False)
    print(f"\nDone. Found {len(records)} parcels in {county} book {book:03d}.")
    print(f"Output: {out_csv}")


if __name__ == "__main__":
    main()
