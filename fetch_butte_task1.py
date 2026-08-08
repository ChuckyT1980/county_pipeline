"""
DEPRECATED 2026-08-08 - DO NOT USE FOR DOSSIER GENERATION.

This script was found (release-integrity audit, commit 27c6cd4) to be a
reachable, unguarded bypass of the redemption-lifecycle filter: it wrote
directly into the real output/dashboard/ directory via
report_builder.build_property_intelligence_dossier() with no
redemption_status check at all - the same class of bug fixed in
regen_butte_dossiers.py (the redeemed Gridley parcel, 022-210-078-000).

The canonical, filtered Butte generation path is regen_butte_dossiers.py
(specifically regen_butte_dossiers.main(), which calls is_redeemed() on
every candidate parcel before generating a dossier). Use that instead -
directly (`python3 regen_butte_dossiers.py`), or via
ca_unify_dashboard.py's "Generate Butte Dossiers" button, which now
calls regen_butte_dossiers.main() in-process rather than shelling out to
this file.

task1c() below is now a hard, unconditional fail-closed guard - it
raises before generating anything, whether this file is run directly or
imported and called as a function. task1a()/task1b() are left
functionally unchanged (data-gathering only, no output/dashboard writes)
purely as an audit trail of what this path used to do - they are never
reachable from __main__ anymore either.
"""
import sys

import csv
from datetime import datetime, timezone
import os
import time

def task1a():
    # Lazy imports: requests/bs4 are only needed if this (now-unreachable
    # from __main__) function is actually called directly - keeping them
    # out of module level means the deprecation guard below can always
    # run and print its message, even in an environment where these
    # optional scraping dependencies were never installed.
    import requests
    from bs4 import BeautifulSoup

    out_dir = "data/counties/butte"
    os.makedirs(out_dir, exist_ok=True)
    out_csv = os.path.join(out_dir, "auction_list_live_2026-08-07.csv")
    
    # Let's try Bid4Assets
    url = "https://www.bid4assets.com/search?countyID=&search=butte+county&statusID=all"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers)
    
    apns = []
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        # Bid4assets cards
        for card in soup.find_all(string=lambda t: "APN:" in t if t else False):
            # very basic extraction - usually APN: 002-650-003-000
            try:
                apn_text = card.parent.get_text(strip=True)
                if "APN:" in apn_text:
                    apn = apn_text.split("APN:")[1].strip().split()[0]
                    if len(apn) > 5:
                        apns.append({
                            "apn": apn,
                            "apn_dash": apn,
                            "address": "",
                            "minimum_bid": "",
                            "opening_bid": "",
                            "source_url": url,
                            "fetch_ts": datetime.now(timezone.utc).isoformat()
                        })
            except:
                pass
                
    if not apns:
        print("Could not fetch from Bid4Assets, attempting local Butte auction CSV fallbacks...")
        fallback_paths = [
            "tax_pipeline/butte_auction_all_105_enriched.csv",
            "butte/butte_15_percent_sample_ENRICHED.csv",
            "butte/butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv",
            "tax_pipeline/butte_auction_targets.csv"
        ]
        chosen_path = None
        for p in fallback_paths:
            if os.path.exists(p):
                chosen_path = p
                break
                
        if chosen_path:
            print(f"Using fallback file: {chosen_path}")
            try:
                with open(chosen_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        raw_apn = row.get("apn") or row.get("apn_dash") or row.get("APN") or ""
                        apn_clean = raw_apn.replace("-", "").strip()
                        if raw_apn:
                            apns.append({
                                "apn": apn_clean,
                                "apn_dash": raw_apn,
                                "address": row.get("address") or row.get("situs_address", ""),
                                "minimum_bid": row.get("minimum_bid") or row.get("min_bid") or row.get("opening_bid", ""),
                                "opening_bid": row.get("opening_bid") or row.get("min_bid", ""),
                                "source_url": "FALLBACK_LOCAL_" + chosen_path,
                                "fetch_ts": datetime.now(timezone.utc).isoformat()
                            })
            except Exception as e:
                print("Fallback read failed:", e)
        else:
            print("No local Butte fallback CSV files found.")
            
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["apn", "apn_dash", "address", "minimum_bid", "opening_bid", "source_url", "fetch_ts"])
        writer.writeheader()
        writer.writerows(apns)
        
    return out_csv, apns

def task1b(in_csv):
    import live_fetch_engine
    out_csv = "data/counties/butte/butte_auction_enriched.csv"
    with open(in_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
    apn_list = [r["apn"] for r in rows if r.get("apn")]
    print(f"Enriching {len(apn_list)} APNs...")
    
    results = live_fetch_engine.batch_fetch("butte", apn_list, rate_limit_s=0.5)
    
    enriched_rows = []
    # Merge
    res_map = {r["apn"]: r for r in results}
    for row in rows:
        apn = row["apn"]
        res = res_map.get(apn, {})
        owner = res.get("owner")
        assessed_value = res.get("assessed_value")
        owner_source = "VERIFIED" if owner else "MPTS_MISS"
        
        enriched_rows.append({
            "apn": apn,
            "apn_dash": row.get("apn_dash", apn),
            "owner": owner,
            "assessed_value": assessed_value,
            "address": row.get("address", ""),
            "minimum_bid": row.get("minimum_bid", ""),
            "owner_source": owner_source,
            "source_url": res.get("source_url") or row.get("source_url"),
            "fetch_ts": res.get("fetch_ts") or datetime.now(timezone.utc).isoformat()
        })
        
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["apn", "apn_dash", "owner", "assessed_value", "address", "minimum_bid", "owner_source", "source_url", "fetch_ts"])
        writer.writeheader()
        writer.writerows(enriched_rows)
        
    return out_csv

DEPRECATION_MESSAGE = (
    "fetch_butte_task1.py is DEPRECATED and DISABLED for dossier generation.\n"
    "It bypassed redemption-lifecycle validation (no is_redeemed() check) - the same\n"
    "bug class fixed for the redeemed Gridley parcel (022-210-078-000) in\n"
    "regen_butte_dossiers.py.\n\n"
    "Use the canonical, filtered Butte generation path instead:\n"
    "  python3 regen_butte_dossiers.py\n"
    "or the \"Generate Butte Dossiers\" button in ca_unify_dashboard.py, which now\n"
    "calls regen_butte_dossiers.main() directly.\n"
)


def task1c(enriched_csv):
    """
    Hard fail-closed guard: this function must never generate output,
    regardless of whether it's reached via __main__ or called directly
    after an import - both are real, previously-reachable paths. Raises
    unconditionally before doing anything else, including opening
    enriched_csv, so it cannot write to output/dashboard/ under any
    calling convention.
    """
    raise RuntimeError(DEPRECATION_MESSAGE)


if __name__ == "__main__":
    print(DEPRECATION_MESSAGE, file=sys.stderr)
    sys.exit(1)
