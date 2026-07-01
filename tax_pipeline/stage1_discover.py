"""
Stage 1: Live Parcel Discovery — JSON API (No Playwright needed)
Uses the confirmed MBC JSON API directly via requests.
API: GET /MBC/api/search/{county}/{year}/{searchType}/{term}
SearchType confirmed: "situs" for street address

Install: pip install requests pandas
Run:     python stage1_discover.py tehama
"""

import re, sys, time
from datetime import datetime
import requests
import pandas as pd
from config import COUNTY_CONFIG

# ── Seeds: street suffixes and common Tehama street name fragments
# All 6+ chars, each returns a different slice of the address index.
# Combined these cover the full county parcel address space.
SEEDS = [
    # Street type suffixes (catch every road/street/etc.)
    "AVENUE", "STREET", "ROAD ST", "DRIVE", "LANE LN", "PLACE PL",
    "COURT CT", "CIRCLE", "TRAIL", "HIGHWAY", "FREEWAY", "PARKWAY",
    "BLVD", "WAY", "LOOP", "RIDGE", "VALLEY", "CREEK", "RANCH",
    "CANYON", "HOLLOW", "MEADOW", "SPRING", "BRIDGE", "GROVE",
    # Common Tehama county street name fragments (6+ chars)
    "MAIN ST", "OAK ST", "ELM ST", "PINE ST", "CEDAR", "WALNUT",
    "ANTELOPE", "TEHAMA", "CORNING", "GERBER", "FLOURNOY",
    "PASKENTA", "PAYNES", "HOOKER", "SOLANO", "SALE LANE",
    "RAWSON", "TOOMES", "DEL PUERTO", "RIO ST", "LASSEN",
    "SHASTA", "TRINITY", "PLUMAS", "BUTTE ST", "YOLO ST",
    "ORANGE ST", "THIRD ST", "SECOND", "FOURTH", "FIFTH ST",
    "SIXTH ST", "SEVENTH", "EIGHTH", "NINTH ST", "TENTH ST",
    "NORTH ST", "SOUTH ST", "EAST ST", "WEST ST",
    "SISTER MARY", "COUNTY RD", "MILL ST", "WATER ST",
    "JACKSON", "LINCOLN", "GRANT ST", "MADISON", "MONROE",
    "WASHINGTON", "HARRISON", "FRANKLIN", "HAMILTON",
    "CALIFORNIA", "Sacramento", "PORTLAND", "NEVADA ST",
    "FOREST", "MOUNTAIN", "RIVER RD", "LAKE RD", "POND RD",
    "ORCHARD", "VINEYARD", "GARDEN", "MARKET", "CHURCH",
    "SCHOOL", "COLLEGE", "MISSION", "ADOBE", "RANCHO",
    "SUNRISE", "SUNSET", "SKYLINE", "HILLTOP", "HILLSIDE",
    "OAKDALE", "RICCA", "KIMBALL", "MARGUERITE", "RANCHERIA",
    "BEEGUM", "PLATINA", "MINERAL", "MCCARTHY", "BOWMAN",
    "HENLEY", "HOOKER CK", "COLD FORK", "BIG BEND",
    "PONY FARM", "TOMHEAD", "BLACK BEAR", "ELDER CK",
    "SULPHUR", "WAGON RD", "ADOBE RD", "BALL PARK",
    "INDUSTRIAL", "COMMERCE", "RAILROAD", "AIRPORT",
]

# Deduplicate seeds
SEEDS = list(dict.fromkeys(SEEDS))


def build_session(cfg: dict) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer":          f"{cfg['host']}{cfg['appFolder']}{cfg['county_slug']}/tax/search",
        "X-Requested-With": "XMLHttpRequest",
        "Accept":           "application/json, text/javascript, */*; q=0.01",
    })
    return s


def search_api(session, cfg: dict, term: str) -> list:
    """Call the JSON API and return raw result list."""
    county = cfg["county_slug"]
    year_api = "0000-CURR" if cfg["tax_year"] == "2025" else cfg["tax_year"]
    host   = cfg["host"]
    app    = cfg["appFolder"]

    url = f"{host}{app}api/search/{county}/{year_api}/situs/{requests.utils.quote(term)}"
    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        
        # The MBC API sometimes double-encodes the JSON (returns a string containing JSON)
        if isinstance(data, str):
            import json
            try:
                data = json.loads(data)
            except Exception:
                pass
                
        # API returns either a list directly, or {"Table": {"Row": [...]}}
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Try common MBC response shapes
            for key in ["Table", "table", "Results", "results", "data"]:
                if key in data:
                    inner = data[key]
                    if isinstance(inner, list):
                        return inner
                    if isinstance(inner, dict):
                        rows = inner.get("Row") or inner.get("row") or []
                        return rows if isinstance(rows, list) else [rows]
        return []
    except Exception as e:
        print(f"  [API error] {term}: {e}")
        return []


def normalize_row(row: dict, county: str, year: str) -> dict | None:
    """
    Normalize a raw API row into our standard schema.
    MBC API fields observed: Asmt, Situs1, Taxyear, Tra, RollCategory, FeeParcel, RollYear
    """
    # Accept various field name casings
    def g(*keys):
        for k in keys:
            v = row.get(k) or row.get(k.lower()) or row.get(k.upper())
            if v:
                return str(v).strip()
        return ""

    asmt_raw = g("Asmt", "asmt", "ASMT")
    if not asmt_raw:
        return None

    # Reformat to dashed if not already: 004130006000 -> 004-130-006-000
    clean = re.sub(r"[^0-9A-Za-z]", "", asmt_raw)
    if len(clean) == 12 and clean.isdigit():
        asmt = f"{clean[0:3]}-{clean[3:6]}-{clean[6:9]}-{clean[9:12]}"
    else:
        asmt = asmt_raw

    tax_year  = g("Taxyear", "TaxYear", "taxyear") or year
    roll_year = g("RollYear", "rollyear") or "0000"
    address   = g("Situs1", "situs1", "Address", "address")
    tra       = g("Tra", "tra", "TRA")
    roll_cat  = g("RollCategory", "rollcategory", "RollCat")
    fee_parcel= g("FeeParcel", "feeparcel", "FeeParcel")

    if fee_parcel and re.match(r'^\d{12}$', fee_parcel):
        fee_parcel = f"{fee_parcel[0:3]}-{fee_parcel[3:6]}-{fee_parcel[6:9]}-{fee_parcel[9:12]}"

    return {
        "asmt":         asmt,
        "asmt_raw":     clean,
        "address":      address,
        "year":         tax_year,
        "roll_year":    roll_year,
        "tra":          tra,
        "roll_cat":     roll_cat,
        "fee_parcel":   fee_parcel,
        "detail_url":   f"https://common1.mptsweb.com/MBC/{county}/tax/main/{clean}/{tax_year}/{roll_year}",
        "county":       county,
        "discovered_at": datetime.utcnow().isoformat(),
    }


def discover(county: str, output_csv: str):
    cfg     = COUNTY_CONFIG[county]
    session = build_session(cfg)
    parcels = {}  # keyed by (asmt, year) — deduplicates across seeds

    print(f"[Stage 1] Starting discovery for {county.upper()} — {len(SEEDS)} seeds")
    print(f"[Stage 1] API base: {cfg['host']}{cfg['appFolder']}api/search/{county}/{cfg['tax_year']}/situs/\n")

    # First, do a warm-up GET on the search page to establish session/cookies
    try:
        session.get(
            f"{cfg['host']}{cfg['appFolder']}{cfg['county_slug']}/tax/search",
            timeout=15
        )
    except:
        pass

    for i, seed in enumerate(SEEDS):
        rows = search_api(session, cfg, seed)
        new_count = 0

        for row in rows:
            norm = normalize_row(row, county, cfg["tax_year"])
            if not norm:
                continue
            key = (norm["asmt"], norm["year"])
            if key not in parcels:
                parcels[key] = norm
                new_count += 1

        status = f"+{new_count} new" if rows else "0 results"
        print(f"  [{i+1:>3}/{len(SEEDS)}] {seed:<20} -> {status}  (total: {len(parcels)})")

        # If API returned results, delay politely; skip delay on empty
        if rows:
            time.sleep(0.5)

    df = pd.DataFrame(list(parcels.values()))
    df.to_csv(output_csv, index=False)
    print(f"\n[OK] Stage 1 done — {len(df)} unique parcels -> {output_csv}")
    return output_csv


if __name__ == "__main__":
    county = sys.argv[1] if len(sys.argv) > 1 else "tehama"
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
    out    = f"{county}_discovery_{ts}.csv"
    discover(county, out)
