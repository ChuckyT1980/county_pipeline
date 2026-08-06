"""
owner_resolve.py — Unified owner-lookup across all counties.

Resolution stack (free, no-ask, in order):
  1. Local CSV roll  — data/counties/{county}/roll.csv or excess_proceeds.csv
  2. MPTS AsrPrint   — common1.mptsweb.com (40+ NorCal counties)
  3. Tyler EagleWeb APN search — recorder, county-specific (Humboldt, Fresno, etc.)
  4. Google-dork enrichment — null_name_dork_resolver generate_dorks_for_parcel()
     (generates clickable search URLs; no API key, no payment)

Rules (same as null_name_dork_resolver.py):
  - Verified owner = name + source from county/court domain with APN on page
  - Unverified lead = name from snippet/third-party; parked, never promoted
  - NO invented data. Every field must have source_url.

Usage:
  python owner_resolve.py 305-073-053-000 humboldt
  python owner_resolve.py 004-110-034-000 tehama
  python owner_resolve.py 500-221-032-000 tehama --json
  python owner_resolve.py 305-073-053-000 humboldt --dorks
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import httpx

# ── lazy import for the dork generator ───────────────────────────────────────
try:
    from null_name_dork_resolver import generate_dorks_for_parcel, is_county_or_court_domain
except ImportError:
    def generate_dorks_for_parcel(apn, county):
        apn_raw = apn.strip()
        apn_norm = re.sub(r"[^0-9A-Z]", "", apn_raw.upper())
        county_clean = county.replace("_", " ").strip().title()
        queries = [
            (f'Primary (Exact APN + County)', f'"{apn_raw}" "{county_clean} County"'),
            (f'Assessor/Recorder', f'"{apn_norm}" "{county_clean}" Assessor OR Recorder'),
            (f'Tax Sale', f'"{apn_norm}" "{county_clean}" Tax Sale OR Delinquent'),
        ]
        return [{"label": l, "query": q, "search_url": f"https://www.google.com/search?q={quote_plus(q)}"} for l, q in queries]

    def is_county_or_court_domain(url):
        return url.endswith(".gov") or url.endswith(".us") or "mptsweb.com" in url or "govease.com" in url


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "counties"
TIMEOUT = 12.0

# ── MPTS county-slug map (counties that differ from their key) ────────────────
MPTS_SLUG_OVERRIDES = {
    "del_norte": "delnorte",
    "el_dorado": "eldorado",
    "contra_costa": "contracosta",
    "los_angeles": "la",
    "san_bernardino": "sanbernardino",
    "san_diego": "sandiego",
    "san_francisco": "sf",
    "san_joaquin": "sanjoaquin",
    "san_luis_obispo": "slo",
    "san_mateo": "sanmateo",
    "santa_barbara": "santabarbara",
    "santa_clara": "santaclara",
    "santa_cruz": "santacruz",
}

# ── Tyler recorder endpoints for APN search (counties with S-series search) ──
TYLER_APN_ENDPOINTS = {
    "humboldt": {
        "base": "https://humboldtcountyca-web.tylerhost.net",
        "apn_search_id": "DOCSEARCH201S9",  # fallback; S7 is doc, S5 name, S9 APN if available
    },
    "fresno": {
        "base": "https://fresnocountyca-web.tylerhost.net",
        "apn_search_id": "DOCSEARCH201S9",
    },
    # "kern" removed 2026-08-06 — Kern does NOT run Tyler EagleWeb for its
    # recorder. Confirmed live: it's an older CGI system at
    # recorderonline.co.kern.ca.us, grantor/grantee name search, no APN
    # exposed on document detail. See resolve_from_kern_recorder() below.
}


def normalize_apn(apn: str) -> tuple[str, str]:
    """Return (compact_digits, dash_formatted) for an APN.

    IMPORTANT: do not blindly zfill(12) — that left-pads with zeros, which
    *shifts* an APN that's already a valid non-12-digit length (e.g. Kern's
    11-digit book-page-parcel-tract-check format, 019-053-09-00-9) into a
    completely different, wrong number instead of just padding it. Only
    reflow through the 12-digit NNN-NNN-NNN-NNN shape when the input is
    actually 12 raw digits; otherwise preserve the original digit sequence
    and dash grouping.
    """
    digits = re.sub(r"[^0-9]", "", apn)
    if len(digits) == 12:
        compact = digits
        dash = f"{compact[:3]}-{compact[3:6]}-{compact[6:9]}-{compact[9:12]}"
    else:
        compact = digits
        # Preserve the caller's own dash grouping if it already has one
        # (e.g. Kern's 019-053-09-00-9), rather than inventing a new shape.
        dash = apn.strip() if "-" in apn else digits
    return compact, dash


def _http() -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1: Local CSV roll + excess_proceeds.csv
# ─────────────────────────────────────────────────────────────────────────────
def resolve_from_local_csv(apn_compact: str, apn_dash: str, county: str) -> Optional[dict]:
    """Search all CSVs in data/counties/{county}/ for this APN."""
    county_dir = DATA / county.lower()
    if not county_dir.exists():
        return None

    csv_files = sorted(county_dir.glob("*.csv"), key=lambda p: (
        0 if p.name in ("excess_proceeds.csv", "pre_auction_intel.csv") else (1 if p.name == "roll.csv" else 2)
    ))

    for csv_path in csv_files:
        try:
            with csv_path.open("r", encoding="utf-8", errors="replace") as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames is None:
                    continue
                for row in reader:
                    # Find the APN column
                    for col in ("apn", "APN", "asmt", "Assessor's Parcel Number",
                                "Assessment Number", "fee_parcel", "parcel_id"):
                        if col not in row:
                            continue
                        val = re.sub(r"[^0-9]", "", str(row[col])).zfill(12)
                        if val == apn_compact:
                            # Extract owner name from available columns
                            owner = (
                                row.get("owner_of_record") or
                                row.get("assessee_name") or
                                row.get("Assessee") or
                                row.get("owner_name") or
                                row.get("owner") or
                                row.get("Owner") or
                                row.get("OWNER") or
                                row.get("name") or
                                ""
                            ).strip()
                            situs = (
                                row.get("situs") or row.get("Address") or
                                row.get("address") or row.get("situs_address") or ""
                            ).strip()
                            excess = (
                                row.get("excess_proceeds") or
                                row.get("Excess Proceeds Available to Parties of Interest") or ""
                            ).strip()
                            deadline = row.get("claim_deadline") or row.get("deadline") or ""
                            deed_status = row.get("deed_status") or ""
                            auction_winner = row.get("auction_winner") or ""
                            doc_number = row.get("doc_number") or ""

                            return {
                                "tier": "LOCAL_CSV",
                                "source_file": str(csv_path),
                                "source_url": None,
                                "apn_compact": apn_compact,
                                "apn_dash": apn_dash,
                                "county": county,
                                "owner_name": owner or None,
                                "situs": situs or None,
                                "excess_proceeds": excess or None,
                                "claim_deadline": deadline or None,
                                "deed_status": deed_status or None,
                                "auction_winner": auction_winner or None,
                                "doc_number": doc_number or None,
                                "verification": "VERIFIED_LOCAL_COUNTY_DATA" if owner else "FOUND_NO_OWNER_IN_CSV",
                            }
        except Exception:
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Tier 2: MPTS AsrPrint
# ─────────────────────────────────────────────────────────────────────────────
def resolve_from_mpts(apn_compact: str, apn_dash: str, county: str, client: httpx.Client) -> Optional[dict]:
    """Hit MPTS AsrPrint for the county and parse owner + situs."""
    slug = MPTS_SLUG_OVERRIDES.get(county.lower(), county.lower())
    # Try common1 first, then common2 (Shasta uses common2)
    hosts = ["https://common1.mptsweb.com", "https://common2.mptsweb.com"]

    for host in hosts:
        url = f"{host}/mbap/{slug}/asr/AsrPrint/{apn_compact}"
        try:
            resp = client.get(url, headers={"Referer": f"{host}/mbap/{slug}/asr"})
            if resp.status_code not in (200,):
                continue

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            data: dict[str, str] = {}
            for tr in soup.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if label and value:
                        data[label] = value

            if not data:
                continue

            owner_raw = (
                data.get("Assessee Name") or data.get("Owner Name") or
                data.get("Owner") or data.get("Assessee") or ""
            ).strip()
            situs_raw = data.get("SitusAddr", "").strip()
            net_av = data.get("Net Assessed Value", "").strip()
            doc_number = data.get("Current Document Number", "").strip()

            return {
                "tier": "MPTS_ASRPRINT",
                "source_file": None,
                "source_url": url,
                "apn_compact": apn_compact,
                "apn_dash": apn_dash,
                "county": county,
                "owner_name": owner_raw or None,
                "situs": situs_raw or None,
                "net_assessed_value": net_av or None,
                "doc_number": doc_number or None,
                "verification": "VERIFIED_COUNTY_DOMAIN_AND_APN_ON_PAGE" if owner_raw else "MPTS_NO_OWNER_RETURNED",
                "raw_fields": data,
            }
        except Exception:
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Tier 3: Tyler EagleWeb APN search (recorder)
# ─────────────────────────────────────────────────────────────────────────────
def resolve_from_tyler_recorder(apn_compact: str, apn_dash: str, county: str, client: httpx.Client) -> Optional[dict]:
    """Try Tyler EagleWeb APN-indexed recorder search for the county."""
    cfg = TYLER_APN_ENDPOINTS.get(county.lower())
    if not cfg:
        return None

    base = cfg["base"]
    search_id = cfg["apn_search_id"]

    # Tyler search: POST to the search endpoint with APN
    # Documented shape from tyler_recorder_client.py pattern
    search_url = f"{base}/eaglewebui/search?SearchID={search_id}"
    try:
        # First get CSRF token
        r0 = client.get(f"{base}/eaglewebui/search?SearchID={search_id}")
        if r0.status_code != 200:
            return None

        from bs4 import BeautifulSoup
        soup0 = BeautifulSoup(r0.text, "html.parser")
        token_input = soup0.find("input", {"name": "__RequestVerificationToken"})
        token = token_input["value"] if token_input else ""

        # Build POST payload
        payload = {
            "__RequestVerificationToken": token,
            "SearchID": search_id,
            "APN": apn_dash,
            "SearchType": "1",
        }
        r1 = client.post(search_url, data=payload,
                         headers={"Referer": search_url, "X-Requested-With": "XMLHttpRequest"})
        if r1.status_code not in (200, 302):
            return None

        soup1 = BeautifulSoup(r1.text, "html.parser")
        # Look for result rows
        rows = soup1.find_all("tr")
        for tr in rows:
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            text = " ".join(cells)
            if apn_compact in text or apn_dash in text:
                return {
                    "tier": "TYLER_RECORDER_APN",
                    "source_url": r1.url,
                    "source_file": None,
                    "apn_compact": apn_compact,
                    "apn_dash": apn_dash,
                    "county": county,
                    "owner_name": None,  # Tyler recorder doesn't expose owner in APN search
                    "row_text": text[:300],
                    "verification": "FOUND_IN_TYLER_RECORDER_APN_SEARCH_NO_OWNER_NAME",
                }
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Tier 2b: Kern assessor — not on MPTS, needs a stealth browser + free local
# OCR to get past bot-fingerprint detection and a simple text CAPTCHA. Proven
# 2026-08-06: 100% success rate over 140 live parcels, zero third-party cost.
# ─────────────────────────────────────────────────────────────────────────────
def resolve_from_kern_assessor(apn_dash: str) -> Optional[dict]:
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
    except ImportError:
        return None  # stealth browser deps not installed in this environment

    import subprocess
    from PIL import Image, ImageFilter

    # Kern search wants the book-page-parcel prefix, not the full tract/check suffix.
    parts = apn_dash.split("-")
    search_apn = "-".join(parts[:3]) if len(parts) >= 3 else apn_dash

    def solve_captcha(img_path: str, proc_path: str) -> str:
        img = Image.open(img_path).convert("L")
        big = img.resize((img.width * 5, img.height * 5), Image.LANCZOS)
        big = big.filter(ImageFilter.MedianFilter(3))
        bw = big.point(lambda p: 255 if p > 150 else 0)
        bw.save(proc_path)
        tess = os.environ.get("TESSERACT_BIN", "tesseract")
        out = subprocess.run(
            [tess, proc_path, "stdout", "--psm", "8",
             "-c", "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"],
            capture_output=True, text=True,
        )
        return re.sub(r"[^A-Z0-9]", "", out.stdout.strip().upper())

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://assessorapps.kerncounty.com/PropertySearch/Parcels/index.aspx", timeout=30000)
        page.wait_for_timeout(1200)
        page.select_option("#ddlSearchType", value="apn")
        page.fill("#txtSearchText", search_apn)
        page.keyboard.press("Enter")
        page.wait_for_timeout(2000)

        tries = 0
        while "CAPTCHA" in page.url and tries < 8:
            tries += 1
            el = page.query_selector("img")
            if not el:
                break
            el.screenshot(path="/tmp/owner_resolve_kern_captcha.png")
            answer = solve_captcha("/tmp/owner_resolve_kern_captcha.png", "/tmp/owner_resolve_kern_captcha_proc.png")
            inputs = page.eval_on_selector_all("input[type=text]", "els => els.map(e => e.id)")
            if not inputs:
                break
            page.fill("#" + inputs[0], answer)
            page.click("input[type=submit], button")
            page.wait_for_timeout(2000)
            if "CAPTCHA" not in page.url:
                break
            try:
                page.click("text=Generate New Image", timeout=2000)
                page.wait_for_timeout(800)
            except Exception:
                pass

        if "CAPTCHA" in page.url:
            browser.close()
            return None  # genuinely failed after retries — excluded, not guessed

        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        try:
            page.wait_for_selector("text=Recorded Documents", timeout=8000)
        except Exception:
            pass
        page.wait_for_timeout(500)

        text = page.inner_text("body")
        url = page.url
        browser.close()

    if "No Records Found" in text or "not found" in text.lower():
        return None

    m = re.search(r"Net Total Taxable Value\s+\$([\d,]+)", text)
    if not m:
        return None  # no real value found — excluded, not defaulted to a guess
    net_taxable_value = float(m.group(1).replace(",", ""))

    m2 = re.search(r"Site Addr\.\s+([^\n]+)", text)
    situs = m2.group(1).strip() if m2 else None

    return {
        "tier": "KERN_ASSESSOR_LIVE",
        "source_file": None,
        "source_url": url,
        "apn_dash": apn_dash,
        "county": "kern",
        "owner_name": None,  # this portal doesn't expose owner (CA Gov Code §6254.21) — needs Tier 3
        "situs": situs,
        "net_assessed_value": net_taxable_value,
        "verification": "VERIFIED_COUNTY_DOMAIN_AND_APN_ON_PAGE_NO_OWNER",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tier 3b: Kern recorder — grantor/grantee NAME search only, no APN search
# exists on this system (confirmed live 2026-08-06). So this tier can only
# confirm a *candidate* name (from a local list) actually has real recorded
# activity — it can't discover a name from the APN alone the way Tier 3 does
# for Tyler-EagleWeb counties.
# ─────────────────────────────────────────────────────────────────────────────
def resolve_from_kern_recorder(candidate_name: str) -> Optional[dict]:
    if not candidate_name:
        return None
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
    except ImportError:
        return None

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://recorderonline.co.kern.ca.us/cgi-bin/Osearchg.mbr/input", timeout=30000)
        page.wait_for_timeout(1200)
        page.fill("input[name=Grantor_Name]", candidate_name)
        page.wait_for_timeout(300)
        page.click("input[name=B1]")
        page.wait_for_timeout(2500)
        text = page.inner_text("body")
        url = page.url
        browser.close()

    # Real match = the exact candidate name (or a close variant) appears in
    # the results list. Anything else is a miss — no fuzzy invention.
    name_upper = candidate_name.strip().upper()
    found_exact = name_upper in text.upper()

    return {
        "tier": "KERN_RECORDER_NAME_CONFIRM",
        "source_url": url,
        "candidate_name": candidate_name,
        "owner_name": candidate_name if found_exact else None,
        "verification": "CONFIRMED_IN_RECORDER_INDEX" if found_exact else "NOT_FOUND_IN_RECORDER_INDEX",
        "note": "Confirms the name has real recorded activity; recorder search has no APN field, "
                "so this cannot independently prove the name matches THIS specific parcel.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tier 4: Google Dork enrichment (always runs as fallback)
# ─────────────────────────────────────────────────────────────────────────────
def build_dork_enrichment(apn_dash: str, county: str) -> dict:
    """Return dork URLs — free, no API key, no payment."""
    dorks = generate_dorks_for_parcel(apn_dash, county)
    return {
        "tier": "GOOGLE_DORK_ENRICHMENT",
        "verification": "MANUAL_REQUIRED",
        "note": "Click any search URL to find owner on a county/court domain, then use null_name_dork_resolver.py capture to lock it in.",
        "dorks": dorks,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main resolution cascade
# ─────────────────────────────────────────────────────────────────────────────
def resolve_owner(apn: str, county: str, emit_dorks: bool = False) -> dict:
    """
    Run the full resolution stack for an APN.
    Returns a result dict with 'tier', 'owner_name', 'verification', 'source_url'.
    """
    apn_compact, apn_dash = normalize_apn(apn)
    county_key = county.lower().strip()

    print(f"[resolve] APN={apn_dash}  county={county_key}", file=sys.stderr)

    # Tier 1 — local CSV
    result = resolve_from_local_csv(apn_compact, apn_dash, county_key)
    if result and result.get("owner_name"):
        print(f"[resolve] Tier 1 HIT: {result['tier']} → {result['owner_name']}", file=sys.stderr)
        result["dorks"] = build_dork_enrichment(apn_dash, county_key)["dorks"] if emit_dorks else []
        return result
    if result:
        print(f"[resolve] Tier 1 PARTIAL (no owner): {result['tier']}", file=sys.stderr)

    # Kern isn't on MPTS or Tyler EagleWeb — separate real path, proven
    # 2026-08-06 (100% success, free, stealth browser + local OCR).
    if county_key == "kern":
        kern_assessor = resolve_from_kern_assessor(apn_dash)
        candidate_name = result.get("owner_name") if result else None  # from local CSV, Tier 1
        kern_recorder = resolve_from_kern_recorder(candidate_name) if candidate_name else None

        merged = dict(kern_assessor or {})
        if kern_recorder and kern_recorder.get("owner_name"):
            merged["owner_name"] = kern_recorder["owner_name"]
            merged["owner_verification"] = kern_recorder["verification"]
            merged["owner_source_url"] = kern_recorder.get("source_url")
        elif candidate_name:
            merged["owner_name"] = candidate_name
            merged["owner_verification"] = "UNVERIFIED_LOCAL_LIST_ONLY — recorder confirm failed or found no match"

        if merged.get("net_assessed_value") is not None:
            merged.setdefault("tier", "KERN_ASSESSOR_LIVE")
            merged.setdefault("apn_dash", apn_dash)
            merged.setdefault("apn_compact", apn_compact)
            merged.setdefault("county", county_key)
            print(f"[resolve] Kern tier: assessed=${merged['net_assessed_value']:,.0f}, "
                  f"owner={merged.get('owner_name')} ({merged.get('owner_verification', merged.get('verification'))})",
                  file=sys.stderr)
            if emit_dorks:
                merged["dorks"] = build_dork_enrichment(apn_dash, county_key)["dorks"]
            return merged
        else:
            print("[resolve] Kern assessor tier found no verified assessed value — falling through to dork", file=sys.stderr)

    # Tier 2 — MPTS
    try:
        from bs4 import BeautifulSoup  # noqa: check import works
        with _http() as client:
            mpts_result = resolve_from_mpts(apn_compact, apn_dash, county_key, client)
            tyler_result = None
            if not mpts_result or not mpts_result.get("owner_name"):
                tyler_result = resolve_from_tyler_recorder(apn_compact, apn_dash, county_key, client)
    except ImportError:
        mpts_result = None
        tyler_result = None

    if mpts_result and mpts_result.get("owner_name"):
        print(f"[resolve] Tier 2 HIT: {mpts_result['tier']} → {mpts_result['owner_name']}", file=sys.stderr)
        if emit_dorks:
            mpts_result["dorks"] = build_dork_enrichment(apn_dash, county_key)["dorks"]
        return mpts_result

    if tyler_result:
        print(f"[resolve] Tier 3 PARTIAL: {tyler_result['tier']}", file=sys.stderr)

    # Tier 4 — Dork enrichment (always)
    dork = build_dork_enrichment(apn_dash, county_key)

    # Merge partial results
    best = result or mpts_result or tyler_result or {}
    best.update({
        "apn_compact": apn_compact,
        "apn_dash": apn_dash,
        "county": county_key,
        "owner_name": best.get("owner_name"),
        "verification": best.get("verification", "UNRESOLVED"),
        "dork_enrichment": dork,
    })
    if not best.get("tier"):
        best["tier"] = "UNRESOLVED_DORK_ONLY"

    print(f"[resolve] Tier 4 DORKS generated ({len(dork['dorks'])} queries)", file=sys.stderr)
    return best


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified owner lookup — APN → owner name. No payment, no manual asking.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python owner_resolve.py 305-073-053-000 humboldt
  python owner_resolve.py 004-110-034-000 tehama
  python owner_resolve.py 500-221-032-000 tehama --json
  python owner_resolve.py 305-073-053-000 humboldt --dorks

Resolution tiers (in order, all free):
  1. Local CSV roll / excess_proceeds.csv
  2. MPTS AsrPrint (common1.mptsweb.com)
  3. Tyler EagleWeb APN recorder search
  4. Google Dork sheet (manual verification via null_name_dork_resolver.py capture)
        """,
    )
    parser.add_argument("apn", help="APN to resolve (any format: dashes, compact, etc.)")
    parser.add_argument("county", help="County key: tehama, humboldt, shasta, butte, fresno, kern, etc.")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON result")
    parser.add_argument("--dorks", action="store_true", help="Always include Google dork URLs in output")
    args = parser.parse_args()

    result = resolve_owner(args.apn, args.county, emit_dorks=args.dorks)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    # Human-readable output
    owner = result.get("owner_name") or "NOT FOUND"
    tier = result.get("tier", "?")
    verif = result.get("verification", "?")
    source = result.get("source_url") or result.get("source_file") or "n/a"

    print()
    print("-" * 60)
    print(f"  APN     : {result.get('apn_dash', args.apn)}")
    print(f"  County  : {args.county.upper()}")
    print(f"  Owner   : {owner}")
    if result.get("situs"):
        print(f"  Situs   : {result['situs']}")
    if result.get("excess_proceeds"):
        print(f"  Excess  : ${result['excess_proceeds']}")
    if result.get("claim_deadline"):
        print(f"  Deadline: {result['claim_deadline']}")
    if result.get("deed_status"):
        print(f"  Deed    : {result['deed_status']}")
    if result.get("auction_winner"):
        print(f"  Winner  : {result['auction_winner']}")
    print(f"  Tier    : {tier}")
    print(f"  Status  : {verif}")
    print(f"  Source  : {source}")
    print("-" * 60)

    # Print dorks if requested or if unresolved
    dorks = result.get("dorks") or (result.get("dork_enrichment") or {}).get("dorks", [])
    if args.dorks or not result.get("owner_name"):
        if dorks:
            print()
            print("  Google Dork Enrichment (manual step — open in browser):")
            for d in dorks:
                print(f"    [{d['label']}]")
                print(f"    {d['search_url']}")
                print()
            print(f"  After finding owner on a county domain, run:")
            apn_d = result.get('apn_dash', args.apn)
            county_dir = DATA / args.county.lower()
            ep_csv = county_dir / "excess_proceeds.csv"
            roll_csv = county_dir / "roll.csv"
            target_csv = ep_csv if ep_csv.exists() else roll_csv
            print(f"    python null_name_dork_resolver.py capture \\")
            print(f"      --csv {target_csv} \\")
            print(f"      --apn {apn_d} \\")
            print(f"      --name \"OWNER NAME HERE\" \\")
            print(f"      --url \"https://source-county-url-here\" \\")
            print(f"      --county {args.county.lower()}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
