"""
Kern County signal scanner via curl-cffi (Akamai bypass without browser).

Uses ASP.NET WebForms POST against assessorapps.kerncounty.com/PropertySearch.
Fast HTTP path — 10-50x faster than Playwright.

Built-in periodic accuracy verification: every N parcels, re-fetch one prior
result and compare — flags any data drift so we know results are consistent.

Usage:
    python kern_signal_scanner.py --limit 50 --workers 5
    python kern_signal_scanner.py --from-csv kern/kern_apn_seed.csv --workers 10
"""
import argparse
import csv
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
SEARCH_URL = "https://assessorapps.kerncounty.com/PropertySearch/Parcels/index.aspx"

# Telerik-specific script/style manager tokens — populated by JS on real browsers.
# Captured from a Playwright-simulated real search 2026-08-01. These are static per
# Telerik build (2026.2.708.462) so safe to hardcode until Kern upgrades Telerik.
TELERIK_TSSM = ";Telerik.Web.UI, Version=2026.2.708.462, Culture=neutral, PublicKeyToken=121fae78165ba3d4:en-US:03a52e94-03ab-4ac2-b277-a6e3154784ef:d7e35272:505983de:959c7879:ba1b8630"
TELERIK_TSM = ";;System.Web.Extensions, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35:en-US:a8328cc8-0a99-4e41-8fe3-b58afac64e45:ea597d4b:b25378d2;Telerik.Web.UI:en-US:03a52e94-03ab-4ac2-b277-a6e3154784ef:16e4e7cd:f7645509:24ee1bba:139673a8:88144a7a:33f3d0c8:874f8ea2:19620875:f46195d3:2003d0b8:aa288e2d:258f1c72:2003d0b8"


def _new_session():
    """Create a curl-cffi session with Chrome impersonation + fetch initial ViewState."""
    s = cffi_requests.Session()
    r = s.get(SEARCH_URL, impersonate="chrome120", timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")
    tokens = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION",
                 "RadStyleSheetManager1_TSSM", "RadScriptManager1_TSM"):
        el = soup.find("input", {"name": name})
        tokens[name] = el.get("value", "") if el else ""
    return s, tokens


def search_apn(session, tokens: dict, apn: str) -> dict:
    """POST an APN search, return parsed result."""
    apn_clean = re.sub(r"[^0-9]", "", apn)

    payload = {
        "RadStyleSheetManager1_TSSM": TELERIK_TSSM,
        "RadScriptManager1_TSM": TELERIK_TSM,
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": tokens.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": tokens.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": tokens.get("__EVENTVALIDATION", ""),
        "ddlSearchType": "apn",
        "txtSearchText": apn_clean,
        "txtSearchText_ClientState": "",
        "btnSearch": "Search",
        "btnSearch_ClientState": "",
        "btnClear_ClientState": "",
    }

    try:
        r = session.post(SEARCH_URL, data=payload, impersonate="chrome120", timeout=20,
                         headers={"Referer": SEARCH_URL})
        if r.status_code != 200:
            return {"apn": apn, "status": f"http_{r.status_code}"}
        return _parse_kern_response(apn, r.text)
    except Exception as e:
        return {"apn": apn, "status": f"err_{str(e)[:40]}"}


def _parse_kern_response(apn: str, html: str) -> dict:
    """Extract owner + situs + values from the Kern search result page."""
    soup = BeautifulSoup(html, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(separator=" "))

    def _grab(pat, default=""):
        m = re.search(pat, text, re.I)
        return m.group(1).strip() if m else default

    def _money(s):
        if not s: return 0
        try: return int(re.sub(r"[^\d]", "", s))
        except: return 0

    # Look for standard Kern assessor field labels
    owner = _grab(r"(?:Owner|Assessee)[^:]*:?\s*([A-Z][A-Z0-9\s&,'\.\-\/]{4,80})(?=Mail|Situs|Address|APN|\d{5})")
    situs = _grab(r"Situs[^:]*:?\s*([\d][\w\s,\.\-\/]{5,100})(?=Mail|APN|Owner|Assessed)")
    mailing = _grab(r"Mailing[^:]*Address[^:]*:?\s*([^:]{10,120}?)(?=APN|Owner|Situs|Assessed)")
    total_val = _money(_grab(r"(?:Total Assessed|Total Value|Assessed Value)[^\$]*\$([\d,]+)"))
    land_val = _money(_grab(r"Land[^\$]{0,20}\$([\d,]+)"))
    imp_val = _money(_grab(r"(?:Improvement|Structural)[^\$]{0,20}\$([\d,]+)"))
    tax_status = _grab(r"(DELINQUENT|CURRENT|PAID|REDEEMED)")

    # Signal score
    signal = 0
    if owner and "trust" in owner.lower(): signal += 10
    if situs and mailing and situs.strip() != mailing.strip(): signal += 25  # absentee
    if total_val >= 100000: signal += 20
    if total_val >= 500000: signal += 15
    if tax_status.upper() == "DELINQUENT": signal += 30

    return {
        "apn": apn,
        "status": "ok" if (owner or situs) else "no_match",
        "owner": owner,
        "situs": situs,
        "mailing": mailing,
        "land_val": land_val,
        "imp_val": imp_val,
        "total_val": total_val,
        "tax_status": tax_status,
        "signal_score": min(100, signal),
    }


def scan(apns: list, workers: int = 5, verify_every: int = 50):
    """Scan APNs with periodic accuracy verification."""
    print(f"Scanning {len(apns)} Kern APNs via curl-cffi (Akamai bypass)...")
    print(f"  Workers: {workers}, verify every {verify_every} parcels")

    results = []
    verification_log = []
    session, tokens = _new_session()
    t0 = time.time()

    def _do_one(apn):
        return search_apn(session, tokens, apn)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_do_one, apn): apn for apn in apns}
        completed = 0
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            completed += 1

            # Periodic accuracy check: re-fetch a prior result, compare
            if completed % verify_every == 0 and len(results) > verify_every:
                sample_idx = completed - verify_every // 2
                sample = results[sample_idx]
                if sample.get("status") == "ok":
                    session2, tokens2 = _new_session()
                    re_row = search_apn(session2, tokens2, sample["apn"])
                    match = (re_row.get("owner") == sample.get("owner") and
                             re_row.get("total_val") == sample.get("total_val"))
                    verification_log.append({
                        "at_row": completed, "apn": sample["apn"],
                        "verified": match,
                        "original_owner": sample.get("owner",""),
                        "reverify_owner": re_row.get("owner",""),
                    })
                    print(f"  [VERIFY at {completed}] APN {sample['apn']}: {'MATCH' if match else 'MISMATCH'}")

            if completed % 25 == 0:
                elapsed = time.time() - t0
                rate = completed / elapsed
                eta = (len(apns) - completed) / rate if rate > 0 else 0
                cands = sum(1 for r in results if r.get("signal_score", 0) >= 30)
                oks = sum(1 for r in results if r.get("status") == "ok")
                print(f"  [{completed:5}/{len(apns)}] {rate:.1f} req/s, ETA {eta/60:.1f} min, {oks} ok, {cands} candidates")

    elapsed = time.time() - t0
    print(f"\nScan complete in {elapsed/60:.1f} min ({len(results)/elapsed:.1f} req/s)")

    out_dir = ROOT / "data" / "kern"
    out_dir.mkdir(parents=True, exist_ok=True)
    full_out = out_dir / "kern_signal_scan_curlcffi.csv"
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

    if verification_log:
        vlog_out = out_dir / "kern_verification_log.csv"
        with open(vlog_out, "w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=list(verification_log[0].keys()))
            w.writeheader()
            w.writerows(verification_log)
        matches = sum(1 for v in verification_log if v["verified"])
        print(f"Verification: {matches}/{len(verification_log)} matched. Log: {vlog_out}")

    cands = sorted([r for r in results if r.get("signal_score", 0) >= 30],
                   key=lambda r: -r.get("signal_score", 0))
    if cands:
        cand_out = out_dir / "kern_signal_candidates.csv"
        with open(cand_out, "w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=list(cands[0].keys()))
            w.writeheader()
            w.writerows(cands)
        print(f"Candidates: {cand_out}")

    print(f"\nTotal scanned: {len(results)}, ok: {sum(1 for r in results if r.get('status')=='ok')}, candidates: {len(cands)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apns", help="Comma-separated APN list")
    p.add_argument("--from-csv", help="CSV path with APN column")
    p.add_argument("--limit", type=int)
    p.add_argument("--workers", type=int, default=5)
    p.add_argument("--verify-every", type=int, default=50)
    args = p.parse_args()

    apns = []
    if args.apns:
        apns = [a.strip() for a in args.apns.split(",") if a.strip()]
    elif args.from_csv:
        with open(args.from_csv, encoding="utf-8") as fp:
            for r in csv.DictReader(fp):
                a = (r.get("parcel_number") or r.get("APN") or r.get("apn") or "").strip()
                if a: apns.append(a)
    else:
        # Default: 20 sample from seed
        default_seed = ROOT / "kern" / "kern_apn_seed.csv"
        if default_seed.exists():
            with open(default_seed, encoding="utf-8") as fp:
                for r in csv.DictReader(fp):
                    apns.append(r["parcel_number"])
        apns = apns[:20]

    if args.limit:
        apns = apns[:args.limit]
    scan(apns, workers=args.workers, verify_every=args.verify_every)
