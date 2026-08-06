"""
Signal Scanner — finds distressed / auction-bound parcels BEFORE the county publishes anything.

For each county's parcel base, hits the MPTS tax bill per APN in parallel and
extracts auction-predictive signals:
  - redemption_status (still delinquent / in default / paid)
  - defaulted_balance (dollar amount owed)
  - years_delinquent (how long unpaid)
  - has_homeowner_exemption (owner-occupied signal)
  - net_taxable_value (parcel worth)

Outputs a candidate list ranked by auction probability.

This lets us produce dossiers on parcels that WILL hit auction weeks or months
before the county's Notice of Sale drops. First-mover advantage.

Usage:
    python signal_scanner.py --county tehama --workers 20
    python signal_scanner.py --county shasta --workers 20 --limit 500
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
    "tehama":   {"tax_year": 2026, "slug": "tehama",   "master": "tehama/tehama_AUTHORITATIVE_master_index.csv",   "apn_col": "parcel_number"},
    "shasta":   {"tax_year": 2025, "slug": "shasta",   "master": "shasta/shasta_AUTHORITATIVE_master_index.csv",   "apn_col": "parcel_number"},
    "humboldt": {"tax_year": 2025, "slug": "humboldt", "master": "archive/tax_pipeline/humboldt_AUTHORITATIVE_master_index.csv", "apn_col": "asmt"},
    "butte":    {"tax_year": 2025, "slug": "butte",    "master": "archive/tax_pipeline/butte_AUTHORITATIVE_master_index.csv",    "apn_col": "parcel_number"},
}


def scan_apn(apn: str, cfg: dict, session: requests.Session) -> dict:
    """Hit MPTS tax bill for one parcel, extract auction-predictive signals only."""
    apn_clean = re.sub(r"[^0-9]", "", apn)
    if len(apn_clean) < 8:
        return {"apn": apn, "status": "invalid"}

    url = (f"https://apps.mptsweb.com/TaxBillv2/RollCatCS.aspx?"
           f"CN={cfg['slug']}&Asmt={apn_clean}&TaxYear={cfg['tax_year']}"
           f"&RollCat=CS&RollType=S&RollYear=")
    referer = f"https://common2.mptsweb.com/mbc/{cfg['slug']}/tax/search"

    try:
        r = session.get(url, headers={"User-Agent": UA, "Referer": referer}, timeout=TIMEOUT)
        if r.status_code != 200 or len(r.text) < 3000:
            return {"apn": apn, "status": f"http_{r.status_code}"}
        text = re.sub(r"<[^>]+>", " ", r.text)
        text = re.sub(r"\s+", " ", text)

        if "try again later" in text.lower():
            return {"apn": apn, "status": "no_bill"}

        def _grab(pat, default=""):
            m = re.search(pat, text, re.I)
            return m.group(1).strip() if m else default

        def _money(s):
            if not s: return 0
            try: return int(re.sub(r"[^\d]", "", s))
            except: return 0

        # Extract signals
        situs = _grab(r"LOCATION:\s*(\d[\w \-\.\/]{5,100}?)(?:TAX RATE|ACRES|COUNTY|IMPORTANT)")
        net_taxable = _money(_grab(r"NET TAXABLE VALUE\s+(\d+)"))
        total_due = _money(_grab(r"TOTAL DUE\s*\$?([\d,]+\.?\d*)"))

        # Redemption / delinquency indicators
        is_delinquent = bool(re.search(r"DELINQUENT AFTER", text, re.I))
        is_redeemed = bool(re.search(r"REDEEMED\s+\d", text, re.I))
        prior_year_balance = _money(_grab(r"PRIOR YEAR[^$]*\$?([\d,]+\.?\d*)"))
        has_hox = _money(_grab(r"Homeowners Exemption[^\$]{0,15}\$?([\d,]+)")) > 0

        # Compute auction risk signal (0-100)
        signal_score = 0
        if is_redeemed:  signal_score = 0  # already paid, off table
        elif is_delinquent:
            signal_score += 30  # any delinquency
            if total_due > 5000:  signal_score += 20
            if total_due > 20000: signal_score += 15
            if prior_year_balance > 0: signal_score += 20  # multi-year delinquency
            if not has_hox: signal_score += 15  # not owner-occupied

        return {
            "apn": apn,
            "status": "ok",
            "situs": situs,
            "net_taxable_value": net_taxable,
            "total_due": total_due,
            "prior_year_balance": prior_year_balance,
            "is_delinquent": is_delinquent,
            "is_redeemed": is_redeemed,
            "has_hox": has_hox,
            "signal_score": min(100, signal_score),
        }
    except requests.RequestException as e:
        return {"apn": apn, "status": f"err_{str(e)[:30]}"}


def scan_county(county: str, workers: int = 20, limit: int = None):
    cfg = COUNTY_CONFIG[county]
    master = ROOT / cfg["master"]
    if not master.exists():
        print(f"ERROR: master index not found at {master}")
        return

    # Read APNs
    with open(master, encoding="utf-8") as fp:
        rows = list(csv.DictReader(fp))
    apns = [r[cfg["apn_col"]].strip() for r in rows if r.get(cfg["apn_col"])]
    if limit:
        apns = apns[:limit]

    print(f"Scanning {len(apns):,} {county} parcels for auction signals using {workers} workers...")
    t0 = time.time()

    results = []
    session = requests.Session()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(scan_apn, apn, cfg, session): apn for apn in apns}
        completed = 0
        for fut in as_completed(futures):
            row = fut.result()
            results.append(row)
            completed += 1
            if completed % 100 == 0:
                elapsed = time.time() - t0
                rate = completed / elapsed
                eta = (len(apns) - completed) / rate if rate > 0 else 0
                candidates = sum(1 for r in results if r.get("signal_score", 0) >= 30)
                print(f"  [{completed:5}/{len(apns)}] {rate:.1f} req/s, ETA {eta/60:.1f} min, {candidates} candidates so far")

    elapsed = time.time() - t0
    print(f"\nScan complete in {elapsed/60:.1f} min ({len(results)/elapsed:.1f} req/s)")

    # Write full results
    out_dir = ROOT / "data" / county
    out_dir.mkdir(parents=True, exist_ok=True)
    full_out = out_dir / f"{county}_signal_scan_full.csv"
    if results:
        keys = list(results[0].keys())
        for r in results:
            for k in r.keys():
                if k not in keys: keys.append(k)
        with open(full_out, "w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=keys)
            w.writeheader()
            w.writerows(results)
        print(f"Full scan saved: {full_out}")

    # Write candidates (signal_score >= 30)
    candidates = sorted([r for r in results if r.get("signal_score", 0) >= 30],
                        key=lambda r: -r.get("signal_score", 0))
    if candidates:
        cand_out = out_dir / f"{county}_auction_candidates.csv"
        with open(cand_out, "w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=list(candidates[0].keys()))
            w.writeheader()
            w.writerows(candidates)
        print(f"Auction candidates ({len(candidates)}) saved: {cand_out}")

    # Print summary
    print("\n=== SUMMARY ===")
    print(f"Total scanned:  {len(results):,}")
    print(f"HTTP ok:        {sum(1 for r in results if r.get('status')=='ok'):,}")
    print(f"Delinquent:     {sum(1 for r in results if r.get('is_delinquent')):,}")
    print(f"Redeemed:       {sum(1 for r in results if r.get('is_redeemed')):,}")
    print(f"Auction candidates (score>=30): {len(candidates):,}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--county", required=True, choices=list(COUNTY_CONFIG.keys()))
    p.add_argument("--workers", type=int, default=20)
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    scan_county(args.county, workers=args.workers, limit=args.limit)
