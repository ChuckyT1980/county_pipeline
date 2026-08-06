"""
Signal Scanner (ArcGIS variant) — for counties whose parcel data lives in a
public ArcGIS FeatureServer (Fresno, Kern in part, etc.).

For each parcel, hits the FeatureServer with a specific-APN filter and extracts
owner + situs + assessed values + homeowner exemption. Filters for
auction-predictive signals: low HOX + high assessed value + non-owner-occupied
patterns.

Note: ArcGIS doesn't include tax delinquency status. That's the signal we lack
here vs. the MPTS scanner. But absentee-owner + high-value + low-HOX patterns
still indicate distress-risk profile.

Usage:
    python signal_scanner_arcgis.py --county fresno --workers 30 --limit 5000
"""
import argparse
import csv
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


ROOT = Path(__file__).parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 15


COUNTY_CONFIG = {
    "fresno": {
        "endpoint": "https://gisprod10.co.fresno.ca.us/server/rest/services/FC_PARCEL_SELECT/MapServer/0/query",
        "master": "fresno/fresno_public_apn_inventory.csv",
        "apn_col": "APN",
        "suffix_fallback": ["S", "T", "U", "ST", "SU", "TS"],
        "fields": ["APN", "NAME1", "SITEADDRESS1", "ADDRESS1", "ADDRESS2",
                   "ASSESS_LAND_VAL", "ASSESS_IMP_VAL", "TOTAL_ASSESSED_VALUE",
                   "HOMEOWNER_EXEMP", "USE_PRIMARY", "LOT_AREA"],
    },
}


def scan_apn(apn: str, cfg: dict, session: requests.Session) -> dict:
    apn_clean = re.sub(r"[^0-9]", "", apn)
    if len(apn_clean) < 5:
        return {"apn": apn, "status": "invalid"}

    def _query(where_apn):
        params = {
            "where": f"APN='{where_apn}'",
            "outFields": ",".join(cfg["fields"]),
            "returnGeometry": "false",
            "f": "json",
        }
        try:
            r = session.get(cfg["endpoint"], params=params, timeout=TIMEOUT,
                            headers={"User-Agent": UA})
            if r.status_code == 200:
                return r.json().get("features", [])
        except requests.RequestException:
            pass
        return []

    feats = _query(apn_clean)
    if not feats and cfg.get("suffix_fallback"):
        for suffix in cfg["suffix_fallback"]:
            feats = _query(apn_clean + suffix)
            if feats:
                break

    if not feats:
        return {"apn": apn, "status": "not_found"}

    a = feats[0].get("attributes", {})
    owner = (a.get("NAME1") or "").strip()
    situs = (a.get("SITEADDRESS1") or "").strip()
    mailing = (a.get("ADDRESS1") or "").strip()
    land = a.get("ASSESS_LAND_VAL") or 0
    imp = a.get("ASSESS_IMP_VAL") or 0
    total = a.get("TOTAL_ASSESSED_VALUE") or 0
    hox = a.get("HOMEOWNER_EXEMP") or 0
    use = (a.get("USE_PRIMARY") or "").strip()

    # Signal score: high-value non-HOX = distress risk
    signal = 0
    if not hox:                              signal += 20   # no homeowner exemption
    if total >= 100000:                       signal += 20   # material value
    if total >= 500000:                       signal += 15   # high value
    if mailing and situs and mailing != situs: signal += 25  # absentee owner
    if imp == 0 and land > 0:                 signal += 10   # vacant land pattern

    return {
        "apn": apn,
        "status": "ok",
        "owner": owner,
        "situs": situs,
        "mailing": mailing,
        "land_val": land,
        "imp_val": imp,
        "total_val": total,
        "has_hox": bool(hox),
        "use_primary": use,
        "signal_score": signal,
    }


def scan_county(county: str, workers: int = 30, limit: int = None):
    cfg = COUNTY_CONFIG[county]
    master = ROOT / cfg["master"]
    if not master.exists():
        print(f"ERROR: master index not found at {master}")
        return

    with open(master, encoding="utf-8") as fp:
        rows = list(csv.DictReader(fp))
    apns = [r[cfg["apn_col"]].strip() for r in rows if r.get(cfg["apn_col"])]
    if limit:
        apns = apns[:limit]

    print(f"Scanning {len(apns):,} {county} parcels via ArcGIS with {workers} workers...")
    t0 = time.time()

    results = []
    session = requests.Session()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(scan_apn, apn, cfg, session): apn for apn in apns}
        completed = 0
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            completed += 1
            if completed % 500 == 0:
                elapsed = time.time() - t0
                rate = completed / elapsed
                eta = (len(apns) - completed) / rate if rate > 0 else 0
                cands = sum(1 for r in results if r.get("signal_score", 0) >= 30)
                print(f"  [{completed:6}/{len(apns)}] {rate:.1f} req/s, ETA {eta/60:.1f} min, {cands} candidates")

    elapsed = time.time() - t0
    print(f"\nScan complete in {elapsed/60:.1f} min ({len(results)/elapsed:.1f} req/s)")

    out_dir = ROOT / "data" / county
    out_dir.mkdir(parents=True, exist_ok=True)
    full_out = out_dir / f"{county}_arcgis_signal_scan_full.csv"
    if results:
        keys = []
        for r in results:
            for k in r.keys():
                if k not in keys: keys.append(k)
        with open(full_out, "w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=keys)
            w.writeheader()
            w.writerows(results)
        print(f"Full scan: {full_out}")

    cands = sorted([r for r in results if r.get("signal_score", 0) >= 30],
                   key=lambda r: -r.get("signal_score", 0))
    if cands:
        cand_out = out_dir / f"{county}_arcgis_candidates.csv"
        with open(cand_out, "w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=list(cands[0].keys()))
            w.writeheader()
            w.writerows(cands)
        print(f"Candidates ({len(cands)}): {cand_out}")

    print(f"\n=== SUMMARY ({county}) ===")
    print(f"Total scanned: {len(results):,}")
    print(f"HTTP ok: {sum(1 for r in results if r.get('status')=='ok'):,}")
    print(f"Candidates (>=30): {len(cands):,}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--county", required=True, choices=list(COUNTY_CONFIG.keys()))
    p.add_argument("--workers", type=int, default=30)
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    scan_county(args.county, workers=args.workers, limit=args.limit)
