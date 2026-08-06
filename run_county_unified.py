"""
Unified CA county parcel extractor — one CLI, 33+ counties.

Reads per-county config and enriches parcels via the appropriate platform
(MPTS or ArcGIS). Outputs normalized CSV to data/{county}/{county}_parcels.csv.

Usage:
    # Enrich a list of APNs for a county:
    python run_county_unified.py --county butte --apns 022-210-078-000,035-143-011-000

    # Enrich from a CSV containing an 'apn' or 'APN' column:
    python run_county_unified.py --county tehama --from-csv tehama/tehama_AUTHORITATIVE_master_index.csv

    # List all configured counties:
    python run_county_unified.py --list

    # Quick single-APN probe (sanity check a county works):
    python run_county_unified.py --county sonoma --probe 001-001-001-000

Behavior:
  - MPTS counties use TaxBillv2 endpoint (returns values + tax status)
  - ArcGIS counties use FeatureServer (returns owner + situs + values where available)
  - Failed APNs logged with reason; nothing fabricated
  - Output CSV includes source URL and _status per row
"""
import argparse
import csv
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from extractor.counties import get_county_config, list_configured_counties


ROOT = Path(__file__).parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 20


# =========================================================================
# MPTS extractor
# =========================================================================

def enrich_mpts(apn: str, cfg: dict, session: requests.Session) -> dict:
    """Fetch and parse an MPTS TaxBillv2 record for one parcel."""
    apn_clean = re.sub(r"[^0-9]", "", apn)
    if len(apn_clean) < 8:
        return {"apn": apn, "_status": "invalid_apn"}

    slug = cfg["mpts_slug"]
    tax_year = cfg["tax_year"]

    def _try(year):
        url = (f"https://apps.mptsweb.com/TaxBillv2/RollCatCS.aspx?"
               f"CN={slug}&Asmt={apn_clean}&TaxYear={year}"
               f"&RollCat=CS&RollType=S&RollYear=")
        referer = f"https://common2.mptsweb.com/mbc/{slug}/tax/search"
        try:
            r = session.get(url, headers={"User-Agent": UA, "Referer": referer}, timeout=TIMEOUT)
            if r.status_code == 200 and len(r.text) >= 3000 and "try again later" not in r.text.lower():
                return url, r.text, year
        except requests.RequestException:
            pass
        return None, None, year

    url, html, used_year = _try(tax_year)
    if not html:
        # Try adjacent years as fallback
        for alt in (tax_year - 1, tax_year + 1, tax_year - 2):
            url, html, used_year = _try(alt)
            if html:
                break
    if not html:
        return {"apn": apn, "county": cfg["county"], "_status": "no_bill_found"}

    return parse_mpts_bill(apn, html, cfg, used_year, url)


def parse_mpts_bill(apn: str, html: str, cfg: dict, tax_year: int, url: str) -> dict:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)

    def _grab(pat, default=""):
        m = re.search(pat, text, re.I)
        return m.group(1).strip() if m else default

    def _money(s):
        if not s: return 0
        try: return int(re.sub(r"[^\d]", "", s))
        except ValueError: return 0

    location = _grab(r"LOCATION:\s*([^A-Z][^0-9]*?[A-Z]{2}\s+\d{5})")
    if not location:
        location = _grab(r"LOCATION:\s*(\d[\w \-\.\/]{5,100}?)(?:TAX RATE|ACRES|COUNTY|IMPORTANT)")

    return {
        "county": cfg["county"],
        "apn": apn,
        "apn_normalized": re.sub(r"[^0-9]", "", apn).zfill(12),
        "tax_year": tax_year,
        "situs_address": location,
        "tax_rate_area": _grab(r"TAX RATE AREA:\s*(\d+)"),
        "acres": _grab(r"ACRES:\s*([\d\.]+)"),
        "land_value": _money(_grab(r"LAND\s+\d+\s+(\d+)")),
        "improvements_value": _money(_grab(r"STRUCTURAL IMPROVEMENTS\s+\d+\s+(\d+)")),
        "personal_prop_value": _money(_grab(r"PERS PROP\s+\d+\s+(\d+)")),
        "net_taxable_value": _money(_grab(r"NET TAXABLE VALUE\s+(\d+)")),
        "total_due": _money(_grab(r"TOTAL DUE\s*\$?([\d,]+\.?\d*)")),
        "redemption_status": _grab(r"(REDEEMED|DELINQUENT|PAID)").lower(),
        "owner_name": "",
        "mailing_address": "",
        "source": "mpts_taxbill",
        "source_url": url,
        "_status": "ok",
    }


# =========================================================================
# ArcGIS extractor
# =========================================================================

def enrich_arcgis(apn: str, cfg: dict, session: requests.Session) -> dict:
    endpoint = cfg["arcgis_endpoint"]
    apn_clean = re.sub(r"[^0-9]", "", apn)

    def _query(where_apn):
        params = {
            "where": f"APN='{where_apn}'",
            "outFields": "*",
            "returnGeometry": "false",
            "f": "json",
        }
        try:
            r = session.get(endpoint, params=params, headers={"User-Agent": UA}, timeout=TIMEOUT)
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
        return {"apn": apn, "county": cfg["county"], "_status": "not_found"}

    a = feats[0].get("attributes", {})
    owner = (a.get("NAME1") or a.get("OWNER_1_FULL_NAME") or a.get("OWNER")
             or a.get("OwnerName") or "")
    situs = (a.get("SITEADDRESS1") or a.get("SITUS_FULL_ADDRESS") or a.get("Situs")
             or a.get("SITUS_ADDRESS") or "")
    mailing = (a.get("ADDRESS1") or a.get("MAILING_FULL_ADDRESS") or a.get("MailingAddress")
               or "")
    land = (a.get("ASSESS_LAND_VAL") or a.get("ASSESSED_LAND_VALUE") or 0)
    imp = (a.get("ASSESS_IMP_VAL") or a.get("ASSESSED_IMPROVEMENT_VALUE") or 0)
    total = (a.get("TOTAL_ASSESSED_VALUE") or a.get("ASSESSED_TOTAL_VALUE") or 0)

    return {
        "county": cfg["county"],
        "apn": apn,
        "apn_normalized": apn_clean.zfill(12),
        "situs_address": situs,
        "owner_name": owner,
        "mailing_address": mailing,
        "land_value": land,
        "improvements_value": imp,
        "net_taxable_value": total,
        "source": "arcgis",
        "source_url": endpoint,
        "_status": "ok",
    }


# =========================================================================
# Orchestrator
# =========================================================================

def enrich_batch(county: str, apns: list, delay: float = 0.5, limit: int = None):
    cfg = get_county_config(county)
    if limit:
        apns = apns[:limit]
    print(f"Enriching {len(apns)} parcels for {county} via {cfg['platform']}...")

    session = requests.Session()
    results = []
    counts = {"ok": 0, "fail": 0, "invalid": 0}

    for i, apn in enumerate(apns, 1):
        if cfg["platform"] == "mpts":
            row = enrich_mpts(apn, cfg, session)
        elif cfg["platform"] == "arcgis":
            row = enrich_arcgis(apn, cfg, session)
        else:
            row = {"apn": apn, "_status": "no_platform"}

        status = row.get("_status", "unknown")
        if status == "ok": counts["ok"] += 1
        elif status == "invalid_apn": counts["invalid"] += 1
        else: counts["fail"] += 1
        results.append(row)

        if i % 5 == 0 or i == len(apns):
            print(f"  [{i:5}/{len(apns)}]  ok={counts['ok']}  fail={counts['fail']}  invalid={counts['invalid']}")
        time.sleep(delay)

    out_dir = ROOT / "data" / county.replace(" ", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{county.replace(' ', '_')}_parcels.csv"
    if results:
        all_keys = []
        for r in results:
            for k in r.keys():
                if k not in all_keys: all_keys.append(k)
        with open(out_path, "w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=all_keys)
            w.writeheader()
            w.writerows(results)
        print(f"\nWrote {out_path}")
        print(f"Summary: {counts['ok']}/{len(apns)} enriched ({100*counts['ok']/len(apns):.0f}%)")
    return counts


def probe_county(county: str, sample_apn: str):
    cfg = get_county_config(county)
    print(f"Probing {county} ({cfg['platform']}) with APN {sample_apn}\n")
    session = requests.Session()
    if cfg["platform"] == "mpts":
        row = enrich_mpts(sample_apn, cfg, session)
    elif cfg["platform"] == "arcgis":
        row = enrich_arcgis(sample_apn, cfg, session)
    else:
        row = {"error": "no platform configured"}
    for k, v in row.items():
        print(f"  {k}: {v}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--county")
    p.add_argument("--apns")
    p.add_argument("--from-csv")
    p.add_argument("--probe", help="Single APN sanity check")
    p.add_argument("--limit", type=int)
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--list", action="store_true")
    args = p.parse_args()

    if args.list:
        counties = list_configured_counties()
        print(f"MPTS counties ({len(counties['mpts'])}):")
        for c in counties["mpts"]: print(f"  {c}")
        print(f"\nArcGIS counties ({len(counties['arcgis'])}):")
        for c in counties["arcgis"]: print(f"  {c}")
        return

    if not args.county:
        p.print_help()
        return

    if args.probe:
        probe_county(args.county, args.probe)
        return

    apns = []
    if args.apns:
        apns = [a.strip() for a in args.apns.split(",") if a.strip()]
    elif args.from_csv:
        with open(args.from_csv, encoding="utf-8") as fp:
            for r in csv.DictReader(fp):
                a = r.get("apn") or r.get("APN") or r.get("parcel_number") or r.get("Parcel_Number")
                if a: apns.append(a.strip())
        print(f"Loaded {len(apns)} APNs from {args.from_csv}")

    if not apns:
        print("ERROR: no APNs provided (use --apns or --from-csv)")
        return

    enrich_batch(args.county, apns, delay=args.delay, limit=args.limit)


if __name__ == "__main__":
    main()
