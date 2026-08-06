import requests
from bs4 import BeautifulSoup
import csv
from datetime import datetime, timezone
import os
import time

def task1a():
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

def task1c(enriched_csv):
    import report_builder
    with open(enriched_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            report_builder.build_property_intelligence_dossier(row, "butte")

if __name__ == "__main__":
    print("Starting Task 1...")
    csv_1a, apns = task1a()
    csv_1b = task1b(csv_1a)
    print("Enrichment done.")
    try:
        task1c(csv_1b)
        print("Dossiers generated.")
    except Exception as e:
        print("Report builder error:", e)
