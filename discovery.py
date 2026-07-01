#!/usr/bin/env python3
"""
Stage 1: County Parcel Discovery Scraper
Builds a complete parcel index from the MBC portal search endpoint.
No prior CSV needed — pulls directly from live county data.

Usage:
    python discovery.py tehama
    python discovery.py eldorado
"""

import csv
import sys
import time
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────
# COUNTY CONFIG
# ─────────────────────────────────────────────
COUNTY_CONFIG = {
    "tehama":   {"host": "common1.mptsweb.com", "slug": "tehama"},
    "eldorado": {"host": "common3.mptsweb.com", "slug": "eldorado"},
    "tulare":   {"host": "common2.mptsweb.com", "slug": "tulare"},
    "kings":    {"host": "common1.mptsweb.com", "slug": "kings"},
    "amador":   {"host": "common1.mptsweb.com", "slug": "amador"},
    "mono":     {"host": "common2.mptsweb.com", "slug": "mono"},
}

TAX_YEAR       = "2025"
REQUEST_DELAY  = 1.0   # seconds between search queries
TIMEOUT        = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded",
}

# ─────────────────────────────────────────────
# SEARCH TERMS
# Street address sweeps — covers virtually all
# Tehama County street names when combined.
# Single letters return all streets starting
# with that letter. Numbers cover rural routes.
# ─────────────────────────────────────────────
ALPHA_TERMS = [chr(c) for c in range(ord('A'), ord('Z') + 1)]

NUMBER_TERMS = [
    "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "HWY", "HIGHWAY", "COUNTY RD", "STATE", "LAKE",
    "RIVER", "CREEK", "RANCH", "VALLEY", "RIDGE",
    "MOUNTAIN", "OAK", "PINE", "CEDAR", "MAPLE",
    "ELDER", "ANTELOPE", "DEER", "BEAR", "DEER",
    "MILL", "SPRING", "ADOBE", "RANCHO", "VISTA",
]

ALL_SEARCH_TERMS = ALPHA_TERMS + NUMBER_TERMS


# ─────────────────────────────────────────────
# SEARCH EXECUTOR
# ─────────────────────────────────────────────
def search_address(session: requests.Session, base_url: str, term: str) -> list[dict]:
    """
    POST a street address search to the MBC portal.
    Returns list of parcel dicts found in results.
    """
    payload = {
        "SelTaxYear":   TAX_YEAR,
        "SearchVal":    "streetaddress",
        "SearchValue":  term,
    }

    try:
        resp = session.post(
            base_url,
            data=payload,
            headers=HEADERS,
            timeout=TIMEOUT
        )
        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code} for term '{term}'")
            return []

        return parse_search_results(resp.text, term)

    except requests.exceptions.Timeout:
        print(f"    Timeout on term '{term}' — skipping")
        return []
    except Exception as e:
        print(f"    Error on term '{term}': {e}")
        return []


# ─────────────────────────────────────────────
# RESULT CARD PARSER
# ─────────────────────────────────────────────
def parse_search_results(html: str, search_term: str) -> list[dict]:
    """
    Parse result cards from the MBC search response.

    Each card contains:
      - Parcel / Fee Parcel number
      - Address
      - Year
      - TRA
      - Roll Category (CS = Current Secured, CU = Current Unsecured)
    """
    soup = BeautifulSoup(html, "html.parser")
    parcels = []

    # MBC renders results as card divs — find all result cards
    # Cards identified by presence of "Fee Parcel" label text
    result_section = soup.find(id="ResultDiv") or soup.find(id="ResultsSecton") or soup

    # Find all card containers — they contain "Fee Parcel :" text
    cards = result_section.find_all("div", class_=lambda c: c and "card" in c.lower())

    # Fallback: find by link pattern /MBC/.../tax/main/
    if not cards:
        links = result_section.find_all("a", href=re.compile(r"/tax/main/"))
        # Group by parent card container
        seen_parents = set()
        card_parents = []
        for link in links:
            parent = link.find_parent("div")
            if parent and id(parent) not in seen_parents:
                seen_parents.add(id(parent))
                card_parents.append(parent)
        cards = card_parents

    for card in cards:
        text = card.get_text(" ", strip=True)

        # Extract parcel number from the heading link
        link = card.find("a", href=re.compile(r"/tax/main/"))
        if not link:
            continue

        href = link.get("href", "")
        # URL format: /MBC/tehama/tax/main/004130006000/2025/0000
        url_match = re.search(r"/tax/main/(\d+)/(\d+)/(\d+)", href)
        if not url_match:
            continue

        parcel_raw  = url_match.group(1)
        year        = url_match.group(2)
        seq         = url_match.group(3)

        # Format parcel back to dashed: 004130006000 -> 004-130-006-000
        parcel_fmt = _format_parcel(parcel_raw)

        # Extract fields from card text
        address      = _card_field(text, "Address")
        tra          = _card_field(text, "TRA")
        roll_cat     = _card_field(text, "Roll Cat")
        fee_parcel   = _card_field(text, "Fee Parcel") or parcel_fmt

        parcels.append({
            "parcel":           parcel_fmt,
            "parcel_raw":       parcel_raw,
            "fee_parcel":       fee_parcel,
            "address":          address or "",
            "year":             year,
            "tra":              tra or "",
            "roll_category":    roll_cat or "",
            "detail_url":       f"https://{{host}}/MBC/{{slug}}/tax/main/{parcel_raw}/{year}/{seq}",
            "search_term":      search_term,
            "discovered_at":    datetime.now(timezone.utc).isoformat(),
        })

    return parcels


def _format_parcel(raw: str) -> str:
    """Convert 12-digit raw parcel to XXX-XXX-XXX-000 format."""
    raw = raw.zfill(12)
    return f"{raw[0:3]}-{raw[3:6]}-{raw[6:9]}-{raw[9:12]}"


def _card_field(text: str, label: str) -> str | None:
    """Extract value after a label in card text."""
    pattern = re.escape(label) + r"[:\s]+([^\n]{1,60}?)(?:\s{2,}|\Z)"
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else None


# ─────────────────────────────────────────────
# DEDUPLICATION
# ─────────────────────────────────────────────
def deduplicate(parcels: list[dict]) -> list[dict]:
    seen = {}
    for p in parcels:
        key = p["parcel_raw"]
        if key not in seen:
            seen[key] = p
    return list(seen.values())


# ─────────────────────────────────────────────
# MAIN DISCOVERY RUNNER
# ─────────────────────────────────────────────
def run_discovery(county: str, output_path: str):
    if county not in COUNTY_CONFIG:
        print(f"ERROR: Unknown county '{county}'")
        print(f"Known counties: {', '.join(COUNTY_CONFIG.keys())}")
        sys.exit(1)

    cfg  = COUNTY_CONFIG[county]
    host = cfg["host"]
    slug = cfg["slug"]
    base_url = f"https://{host}/MBC/{slug}/tax/search"

    print("=" * 60)
    print(f"  STAGE 1: PARCEL DISCOVERY")
    print(f"  County  : {county.upper()}")
    print(f"  Portal  : {base_url}")
    print(f"  Queries : {len(ALL_SEARCH_TERMS)} search terms")
    print(f"  Output  : {output_path}")
    print("=" * 60)

    all_parcels = []
    session = requests.Session()

    # Prime the session — get a valid session cookie
    session.get(f"https://{host}/MBC/{slug}/tax/search", timeout=TIMEOUT)
    time.sleep(0.5)

    for i, term in enumerate(ALL_SEARCH_TERMS):
        print(f"  [{i+1:>3}/{len(ALL_SEARCH_TERMS)}] Searching '{term}'...", end=" ", flush=True)

        results = search_address(session, base_url, term)

        # Inject host/slug into detail URLs
        for r in results:
            r["detail_url"] = r["detail_url"].format(host=host, slug=slug)

        all_parcels.extend(results)
        print(f"{len(results):>4} results  (running total: {len(all_parcels)})")
        time.sleep(REQUEST_DELAY)

    # Deduplicate
    unique = deduplicate(all_parcels)

    print(f"\n  Raw results    : {len(all_parcels)}")
    print(f"  Unique parcels : {len(unique)}")

    # Write index CSV
    if unique:
        fieldnames = [
            "parcel", "fee_parcel", "address", "year",
            "tra", "roll_category", "detail_url",
            "search_term", "discovered_at", "parcel_raw"
        ]
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(unique)

    print(f"\n[Discovery Complete]")
    print(f"  Parcel index written -> {output_path}")
    print(f"  Feed this file into verifier.py as your input CSV")
    print(f"  Run: python verifier.py {county} {output_path} audit.csv crm.csv")
    print("=" * 60)


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    county = sys.argv[1].lower() if len(sys.argv) > 1 else "tehama"
    output = sys.argv[2] if len(sys.argv) > 2 else f"{county}_parcel_index.csv"

    run_discovery(county, output)
