"""
Fresno County parcel data — 100% public sources, no paid dependencies.

Sources used (all free, all public, all responsive as of 2026-07-30):
  1. Fresno ArcGIS: gisprod10.co.fresno.ca.us/server/rest/services/REGIONAL_VIEWS/ASSESSOR_MAP_PAGES
     - Gives us: complete APN inventory (315,312 parcels), assessor map TIF URL per APN
  2. Fresno per-APN assessor lookup (public web page): planned per-parcel scrape

Usage:
    python fresno_public_source_pull.py --sample 20      # test with 20 parcels
    python fresno_public_source_pull.py --apns 001-010-001,001-010-002
    python fresno_public_source_pull.py --all-apns       # dump full 315k APN inventory

Outputs to fresno/fresno_public_apn_inventory.csv (base) and
fresno/fresno_public_enriched.csv (per-APN detail).
"""
import argparse
import csv
import os
import sys
import time

import requests

FRESNO_DIR = os.path.dirname(os.path.abspath(__file__))
INVENTORY_CSV = os.path.join(FRESNO_DIR, "fresno_public_apn_inventory.csv")

ARCGIS_QUERY = (
    "https://gisprod10.co.fresno.ca.us/server/rest/services/"
    "REGIONAL_VIEWS/ASSESSOR_MAP_PAGES/MapServer/0/query"
)

HEADERS = {
    "User-Agent": (
        "LogicFlowSystems/1.0 (mrt@logicflowsystems.io) "
        "CA county tax auction intelligence"
    ),
    "Accept": "application/json",
}


def fetch_apn_batch(offset: int, limit: int = 2000) -> list[dict]:
    """Fetch a page of APNs from Fresno's public ArcGIS layer."""
    params = {
        "where": "1=1",
        "outFields": "APN,URL",
        "resultOffset": offset,
        "resultRecordCount": limit,
        "returnGeometry": "false",
        "orderByFields": "APN ASC",
        "f": "json",
    }
    r = requests.get(ARCGIS_QUERY, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    return [f["attributes"] for f in data.get("features", [])]


def fetch_total_count() -> int:
    r = requests.get(
        ARCGIS_QUERY,
        params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("count", 0)


def dump_full_inventory(out_path: str, page_size: int = 2000) -> int:
    """Pull all 315k+ APNs from the public ArcGIS layer, save to CSV."""
    total = fetch_total_count()
    print(f"Total Fresno parcels in public ArcGIS: {total:,}")
    print(f"Paging at {page_size:,} per request. ETA ~{total // page_size // 30 + 1} min at 30 req/min.")

    seen = 0
    with open(out_path, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["APN", "URL"])
        writer.writeheader()
        offset = 0
        while offset < total:
            batch = fetch_apn_batch(offset, page_size)
            if not batch:
                break
            writer.writerows(batch)
            seen += len(batch)
            print(f"  {seen:,} / {total:,} ({100*seen/total:.1f}%)")
            offset += page_size
            time.sleep(0.5)  # be polite; no rate-limit issues seen but stay under the radar
    return seen


def sample_pull(n: int = 20, out_path: str | None = None) -> list[dict]:
    """Pull a small sample to verify the endpoint works."""
    batch = fetch_apn_batch(0, n)
    print(f"Sample of {len(batch)} Fresno parcels:")
    for i, row in enumerate(batch, 1):
        print(f"  {i}. APN {row.get('APN')}  URL {row.get('URL')}")
    if out_path:
        with open(out_path, "w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=["APN", "URL"])
            writer.writeheader()
            writer.writerows(batch)
        print(f"\nSaved to {out_path}")
    return batch


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=0,
                   help="Pull N sample parcels and print (does not save unless --out).")
    p.add_argument("--all-apns", action="store_true",
                   help="Dump full 315k+ APN inventory to fresno_public_apn_inventory.csv.")
    p.add_argument("--out", default=None, help="Optional output path for --sample.")
    args = p.parse_args()

    if args.all_apns:
        n = dump_full_inventory(INVENTORY_CSV)
        print(f"\nDone. Wrote {n:,} parcels to {INVENTORY_CSV}")
    elif args.sample:
        sample_pull(args.sample, args.out)
    else:
        # Default: prove it works with a 10-parcel sample
        sample_pull(10)
