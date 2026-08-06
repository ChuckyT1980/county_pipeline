"""
live_fetch_engine.py — On-demand live county data fetcher (CA-UNIFY core)

Pulls owner name, assessed value, and tax status from live county portals.
Never reads cached CSVs. Tags every result with provenance + timestamp.
Isolated per-county: if one county fails, it logs the error and returns a 
structured FAIL result — other counties continue unaffected.

Usage:
  python live_fetch_engine.py --county butte --apn 002-650-003-000
  python live_fetch_engine.py --county butte --apn-file data/counties/butte/auction_list_live_2026-08-07.csv --out output/live_fetch_results.json
"""

import requests, time, json, argparse, csv
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import raw_storage_manager
raw_storage_manager.init_raw_storage_schema()

# MPTS host mapping — common2 for Butte and Shasta, common1 for everyone else
MPTS_HOSTS = {
    "butte":  "common2.mptsweb.com",
    "shasta": "common2.mptsweb.com",
}
MPTS_HOST_DEFAULT = "common1.mptsweb.com"

TYLER_ENDPOINTS = {
    "butte":    "https://recorder.buttecounty.net",
    "tehama":   "https://recorder.tehama.ca.us",
    "humboldt": "https://recorder.humboldtgov.org",
    "shasta":   "https://recorderselfservice.shastacounty.gov",
}

TYLER_SEARCH_IDS = {
    "butte":    "DOCSEARCH481S1",
    "tehama":   "DOCSEARCH4S1",
    "humboldt": "DOCSEARCH201S9",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}


def fetch_mpts(county: str, apn: str, session: requests.Session) -> dict:
    """
    Live MPTS assessor lookup.
    Returns: apn, owner, assessed_value, source_url, fetch_ts, status
    status: VERIFIED | MPTS_MISS | MPTS_ERROR
    """
    apn_clean = apn.replace("-", "").replace(" ", "")
    host = MPTS_HOSTS.get(county.lower(), MPTS_HOST_DEFAULT)
    apn_zfill = apn_clean.zfill(12)
    url = f"https://{host}/mbap/{county.lower()}/asr/AsrPrint/{apn_zfill}"
    ts = datetime.now(timezone.utc).isoformat()
    result = {"apn": apn, "source_url": url, "fetch_ts": ts, "status": "MPTS_MISS", "owner": None, "assessed_value": None}
    try:
        resp = session.get(url, headers=HEADERS, timeout=15)
        
        # Store 100% raw capture payload
        try:
            raw_storage_manager.store_raw_capture(county, apn, "assessor_mpts", url, resp.text, {"apn": apn})
        except Exception as se:
            print(f"[raw_storage] Warning: {se}")

        if resp.status_code == 404:
            return result

        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Comprehensive MPTS field extraction
        field_map = {}
        for row in soup.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                val = cells[1].get_text(strip=True)
                field_map[label] = val

        owner = None
        for k, v in field_map.items():
            if "assessee" in k or ("owner" in k and "exemption" not in k and "homeowner" not in k):
                owner = v
                break

        # Parsed structured values
        land_val      = field_map.get("land") or "$0"
        struct_val    = field_map.get("structural imprv") or field_map.get("structure") or "$0"
        net_val       = field_map.get("net assessed value") or field_map.get("total land & improvemnets") or "$0"
        doc_num       = field_map.get("current document number") or field_map.get("doc number")
        deed_dt       = field_map.get("current document  date") or field_map.get("current document date")
        situs_addr    = field_map.get("situsaddr") or field_map.get("situs")
        prop_type     = field_map.get("property type")
        lot_size      = field_map.get("lot size(acres)")
        tra_code      = field_map.get("tax rate area(tra)")

        # If owner is missing, resolve owner via owner_resolve cascade
        if not owner:
            try:
                import owner_resolve
                resolved_res = owner_resolve.resolve_owner(apn, county)
                if resolved_res and isinstance(resolved_res, dict) and resolved_res.get("owner_name"):
                    owner = resolved_res.get("owner_name")
            except Exception:
                pass

        result["owner"]            = owner
        result["assessed_value"]   = net_val
        result["land_value"]       = land_val
        result["structure_value"]  = struct_val
        result["doc_number"]       = doc_num
        result["deed_date"]        = deed_dt
        result["situs"]            = situs_addr
        result["property_type"]    = prop_type
        result["lot_size"]         = lot_size
        result["tax_rate_area"]    = tra_code
        result["status"]           = "VERIFIED" if (owner or net_val != "$0") else "MPTS_MISS"
        
        # Store parsed provenance fields
        try:
            raw_storage_manager.store_raw_capture(county, apn, "assessor_mpts_parsed", url, resp.text, result)
        except Exception:
            pass
    except Exception as e:
        result["status"] = "MPTS_ERROR"
        result["error"] = str(e)
    return result


def fetch_county_parcel(county: str, apn: str, session: requests.Session) -> dict:
    """
    Master orchestrator. Tries MPTS first.
    ALWAYS returns a result dict — never raises.
    """
    result = {
        "apn": apn, "county": county,
        "owner": None, "assessed_value": None, "doc_number": None,
        "source_url": None, "data_source": "LIVE_PORTAL_FETCH",
        "fetch_ts": datetime.now(timezone.utc).isoformat(),
        "status": "PENDING", "error": None,
    }
    try:
        mpts = fetch_mpts(county, apn, session)
        result.update(mpts)
    except Exception as e:
        result["error"] = f"MPTS_EXCEPTION: {e}"
        result["status"] = "MPTS_ERROR"
    return result


def batch_fetch(county: str, apn_list: list, rate_limit_s: float = 1.5) -> list:
    """
    Fetches a list of APNs for one county.
    If 3 consecutive errors occur: logs COUNTY_CIRCUIT_OPEN and returns what we have.
    """
    results = []
    consecutive_errors = 0
    session = requests.Session()
    for apn in apn_list:
        r = fetch_county_parcel(county, apn, session)
        results.append(r)
        if r.get("status") in ("MPTS_ERROR", "TYLER_ERROR"):
            consecutive_errors += 1
        else:
            consecutive_errors = 0
        if consecutive_errors >= 3:
            results.append({
                "county": county, "status": "COUNTY_CIRCUIT_OPEN",
                "error": "3 consecutive errors — county sandboxed, other counties unaffected",
                "fetch_ts": datetime.now(timezone.utc).isoformat()
            })
            break
        time.sleep(rate_limit_s)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live county data fetcher")
    parser.add_argument("--county", required=True, help="County slug (e.g. butte, tehama)")
    parser.add_argument("--apn", help="Single APN lookup")
    parser.add_argument("--apn-file", help="CSV file with 'apn' column for batch run")
    parser.add_argument("--out", default="output/live_fetch_results.json")
    args = parser.parse_args()

    if args.apn:
        session = requests.Session()
        result = fetch_county_parcel(args.county, args.apn, session)
        print(json.dumps(result, indent=2))
    elif args.apn_file:
        with open(args.apn_file, encoding="utf-8") as f:
            apns = [row["apn"] for row in csv.DictReader(f) if row.get("apn")]
        print(f"Fetching {len(apns)} APNs for {args.county}...")
        results = batch_fetch(args.county, apns)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        verified = sum(1 for r in results if r.get("status") == "VERIFIED")
        print(f"Done. {verified}/{len(results)} verified. Output: {args.out}")
    else:
        parser.error("Provide --apn or --apn-file")
