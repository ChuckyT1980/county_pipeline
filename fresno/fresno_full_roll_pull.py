"""
fresno_full_roll_pull.py

Pull the complete Fresno County assessor roll (all APN-populated parcels)
from the public FC_PARCEL_SELECT ArcGIS service — all 42 attribute fields,
paged at 2,000/request. ~3-4 minutes for ~441k parcels.

Output:
    fresno/fresno_full_roll_enriched.csv   (full database)

100% public source, no auth, no CAPTCHA. This is the base parcel database;
auction lists (Notice of Sale / Realauction preview) are filters on it.
"""
import csv
import os
import time

import requests

FRESNO_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_CSV = os.path.join(FRESNO_DIR, "fresno_full_roll_enriched.csv")

ENDPOINT = (
    "https://gisprod10.co.fresno.ca.us/server/rest/services/"
    "FC_PARCEL_SELECT/MapServer/0/query"
)
WHERE = "APN IS NOT NULL AND APN <> ''"
PAGE_SIZE = 2000
DELAY = 0.4

HEADERS = {
    "User-Agent": (
        "LogicFlowSystems/1.0 (mrt@logicflowsystems.io) "
        "CA county tax auction intelligence"
    ),
    "Accept": "application/json",
}


def fetch_total() -> int:
    r = requests.get(ENDPOINT, params={"where": WHERE, "returnCountOnly": "true", "f": "json"},
                     headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json().get("count", 0)


def fetch_page(offset: int) -> list[dict]:
    params = {
        "where": WHERE,
        "outFields": "*",
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
        "returnGeometry": "false",
        "f": "json",
    }
    r = requests.get(ENDPOINT, params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return [f["attributes"] for f in r.json().get("features", [])]


def main():
    total = fetch_total()
    print(f"Total APN-populated parcels: {total:,}")

    # Discover field names from the first page.
    page0 = fetch_page(0)
    fieldnames = list(page0[0].keys())

    seen = 0
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        offset = 0
        while offset < total:
            batch = fetch_page(offset)
            if not batch:
                print(f"  empty batch at offset {offset} — stopping")
                break
            writer.writerows(batch)
            seen += len(batch)
            print(f"  {seen:,} / {total:,} ({100*seen/total:.1f}%)", flush=True)
            offset += PAGE_SIZE
            time.sleep(DELAY)

    print(f"\nWrote {seen:,} parcels ({len(fieldnames)} fields) to {OUT_CSV}")


if __name__ == "__main__":
    main()
