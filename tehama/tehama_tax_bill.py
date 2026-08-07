"""
Tehama County MPTS tax bill scraper.

Same MPTS platform as Butte. Only differences:
  - CN=tehama (not butte)
  - TaxYear=2026 (Tehama's current fiscal year is 2026-2027)

Reuses the parser from butte/tax_bill.py where possible.

Usage:
    python tehama_tax_bill.py --sample 10
    python tehama_tax_bill.py --apns 007-490-016-000,007-490-014-000
    python tehama_tax_bill.py --from-master
"""
import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

import requests

TEHAMA_DIR = Path(__file__).parent
REPO_ROOT = TEHAMA_DIR.parent
MASTER = TEHAMA_DIR / "tehama_AUTHORITATIVE_master_index.csv"
HTML_DIR = TEHAMA_DIR / "tax_bills"
OUT_CSV = TEHAMA_DIR / "tehama_tax_bill_enriched.csv"

BASE_URL = "https://apps.mptsweb.com/TaxBillv2/RollCatCS.aspx"
REFERER = "https://common2.mptsweb.com/mbc/tehama/tax/search"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
COUNTY = "tehama"
TAX_YEAR = 2026


def fetch_tax_bill(apn: str, save: bool = True) -> str | None:
    apn_clean = re.sub(r"[^0-9]", "", apn)
    if len(apn_clean) < 8:
        return None
    url = (f"{BASE_URL}?CN={COUNTY}&Asmt={apn_clean}&TaxYear={TAX_YEAR}"
           f"&RollCat=CS&RollType=S&RollYear=")
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Referer": REFERER}, timeout=20)
        if r.status_code != 200 or len(r.text) < 3000 or "try again later" in r.text.lower():
            return None
        if save:
            HTML_DIR.mkdir(parents=True, exist_ok=True)
            (HTML_DIR / f"{apn_clean}.html").write_text(r.text, encoding="utf-8")
        return r.text
    except requests.RequestException:
        return None


def parse_tax_bill(html: str) -> dict:
    """Extract key fields from the MPTS TaxBillv2 HTML."""
    if not html:
        return {}
    # Strip HTML for pattern matching
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)

    def _grab(pat, default=""):
        m = re.search(pat, text, re.I)
        return m.group(1).strip() if m else default

    def _money(s):
        if not s:
            return 0
        try:
            return int(re.sub(r"[^\d]", "", s))
        except ValueError:
            return 0

    apn = _grab(r"ASMT NUMBER:\s*([\d\-]+)")
    situs = _grab(r"LOCATION:\s*([^A-Z][^0-9]*?[A-Z]{2}\s+\d{5})")
    if not situs:
        situs = _grab(r"LOCATION:\s*(\d[\w \-\.\/]{5,100}?)(?:TAX RATE|ACRES|COUNTY|IMPORTANT)")
    tra = _grab(r"TAX RATE AREA:\s*(\d+)")
    acres = _grab(r"ACRES:\s*([\d\.]+)")
    land = _money(_grab(r"LAND\s+\d+\s+(\d+)"))
    improvements = _money(_grab(r"STRUCTURAL IMPROVEMENTS\s+\d+\s+(\d+)"))
    net_taxable = _money(_grab(r"NET TAXABLE VALUE\s+(\d+)"))
    total_due = _money(_grab(r"TOTAL DUE\s*\$?([\d,]+\.?\d*)"))

    # BUG FIX 2026-08-06: the old `_grab(r"(REDEEMED|DELINQUENT|PAID)")` matched
    # the generic "1st INSTALLMENT ... DELINQUENT AFTER 12/10/2026" boilerplate
    # that appears on every single bill (it describes the due-date rule, not
    # actual default status) — confirmed on a 100-parcel sample: 99/99 falsely
    # showed "delinquent" while only 4/99 had a real default marker on the page.
    # The genuine signal is the specific "Prior year delinquent taxes exist"
    # notice with a default case number and date.
    default_match = re.search(r"Default #(\S+), default date (\d{2}/\d{2}/\d{4})", text)
    is_in_default = bool(default_match)
    default_case_number = default_match.group(1) if default_match else ""
    default_date = default_match.group(2) if default_match else ""

    return {
        "apn": apn,
        "situs_from_tax": situs,
        "tax_rate_area": tra,
        "acres": acres,
        "land_value": land,
        "improvements_value": improvements,
        "net_taxable_value": net_taxable,
        "total_due": total_due,
        "is_in_default": is_in_default,
        "default_case_number": default_case_number,
        "default_date": default_date,
    }


def enrich_batch(apns, delay=0.5, out_path=None, offset=0):
    out_path = out_path or OUT_CSV
    results = []
    total = len(apns)
    for i, apn in enumerate(apns, 1):
        html = fetch_tax_bill(apn)
        if html:
            parsed = parse_tax_bill(html)
            parsed["source_apn"] = apn
            results.append(parsed)
            print(f"  [{offset+i:6}/{offset+total}] {apn}  land=${parsed['land_value']:,}  imp=${parsed['improvements_value']:,}  net=${parsed['net_taxable_value']:,}")
        else:
            print(f"  [{offset+i:6}/{offset+total}] {apn}  FAIL")
        time.sleep(delay)
    if results:
        with open(out_path, "w", newline="", encoding="utf-8") as fp:
            keys = list(results[0].keys())
            w = csv.DictWriter(fp, fieldnames=keys)
            w.writeheader()
            w.writerows(results)
        print(f"\nSaved {len(results)} rows to {out_path}")
    return len(results)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=0)
    p.add_argument("--apns", type=str, default="")
    p.add_argument("--from-master", action="store_true")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--out", type=str, default="")
    p.add_argument("--delay", type=float, default=0.5)
    args = p.parse_args()

    if args.count:
        with open(MASTER, encoding="utf-8") as fp:
            all_apns = [r["parcel_number"] for r in csv.DictReader(fp)]
        apns = all_apns[args.offset:args.offset + args.count]
        print(f"Enriching Tehama chunk: offset={args.offset}, count={len(apns)} of {len(all_apns):,} total")
    elif args.sample:
        with open(MASTER, encoding="utf-8") as fp:
            reader = csv.DictReader(fp)
            apns = [r["parcel_number"] for r in list(reader)[:args.sample]]
    elif args.apns:
        apns = [a.strip() for a in args.apns.split(",") if a.strip()]
    elif args.from_master:
        with open(MASTER, encoding="utf-8") as fp:
            apns = [r["parcel_number"] for r in csv.DictReader(fp)]
        print(f"Enriching all {len(apns):,} Tehama parcels from master index...")
    else:
        # Default: 5 sample from master
        with open(MASTER, encoding="utf-8") as fp:
            apns = [r["parcel_number"] for r in list(csv.DictReader(fp))[:5]]
        print(f"No args — testing with 5 samples")

    out_path = Path(args.out) if args.out else (TEHAMA_DIR / f"tehama_tax_bill_offset{args.offset}.csv" if args.count else OUT_CSV)
    enrich_batch(apns, delay=args.delay, out_path=out_path, offset=args.offset)
