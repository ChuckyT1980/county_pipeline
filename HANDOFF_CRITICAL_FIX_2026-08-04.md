# CRITICAL FIX HANDOFF — Logic Flow Systems County Pipeline
**Date:** 2026-08-04 17:49 PDT
**Owner:** Chuck Terrell | mrt@logicflowsystems.io
**Workspace:** `C:\Users\chuck\Downloads\county_pipeline\`
**Agent Rule #1:** Read this entire document. Then start on Task 1. Do not ask Chuck anything unless you are completely blocked.

---

## THE BIG PICTURE — WHY THIS EXISTS

Chuck is building a California property tax intelligence platform with two revenue legs:

### Revenue Leg 1 — Property Intelligence (Pre-Auction)
Pull delinquent parcel data from CA county public portals *before* the auction. Score it, enrich it, package it as dossiers + call sheets. Sell to real estate investors before they bid.
- Catalog (all parcels ranked): **$47–$97 per county per buyer**
- Deep dossier (one parcel, full detail): **$97–$149 per parcel**
- Do the work once per county. Sell to 10–30 investors going to the same auction.

### Revenue Leg 2 — Excess Proceeds Recovery (Post-Auction)
After a tax auction, if sale price > what was owed, the former owner gets the surplus. They have 1 year (CA R&TC §4675) before it escheats to the county. Chuck finds them, files the claim, takes 30–40% contingency. **No upfront cost to the former owner.**

The hedge: Excess proceeds fills revenue gaps between auction cycles. Counter-cyclical by design.

### The Larger Vision
This is a **public records intelligence framework** deployed first in CA county property tax data. The adapter pattern — a few vendor platforms (Tyler EagleWeb, MPTS, ArcGIS) cover all 58 CA counties — is generalized enough to extend to probate records, UCC liens, building permits, court judgments, and any fragmented government data market.

**Replacement cost if you rebuilt this from scratch:** $36K–$120K.
**With one paying customer:** $1.5M–$5M.
**With national expansion:** $3M–$10M.

### What "Done" Looks Like
A single command — `python county_query_engine.py --county kern --mode prop_intel` — pulls live data from the county portal, enriches every parcel with owner + assessed value, scores it, and drops a ready-to-sell dossier package in `output/dashboard/`. No waiting for county file drops. No static CSVs. One county failing never stops the others.

---

## THE SHORT PICTURE — WHERE WE ARE RIGHT NOW

### What's Working ✅
| Asset | Status |
|---|---|
| Humboldt excess proceeds | 207 claim reports generated, 0 missing owners, $635,951 in surplus |
| Fresno prop intel dossiers | 50 dossiers generated, auction Sept 10–11 |
| Tehama prop intel dossiers | 5 dossiers generated, auction tentative 2027 |
| Butte delivery package | 105 dossiers built (July 29 delivery), teaser sent to Jeff |
| Auction calendar | 108-entry 2025–2027 CA calendar tracking all 58 counties |
| Circuit breaker | Live on Tehama — correctly refusing to run on bad data |
| Dashboard feed | 200 entries across Humboldt, Fresno, Tehama |

### What's Broken ❌ (in priority order)

**PROBLEM 1 — BUTTE AUCTION IN 3 DAYS, NO FRESH DOSSIERS**
- The Aug 7–10 re-offer sale has **104 active parcels, $5.05M total default**
- The July 29 delivery package exists, but that was the *main* sale — the re-offer list is different
- `archive/tax_pipeline/butte_AUTHORITATIVE_master_index.csv` has 90,899 APNs but NO tax_deed flags, NO owners
- The fresh re-offer parcel list must be fetched live from Bid4Assets/Butte Tax Collector portal
- MPTS host for Butte: `common2.mptsweb.com`
- Tyler recorder: `https://recorder.buttecounty.net` (DOCSEARCH481S1)

**PROBLEM 2 — TEHAMA CIRCUIT BREAKER HALTED**
- 4/5 sample Tehama APNs returned null owner — circuit breaker correctly blocked execution
- Only 14 owners filled of 40,059 total parcels
- Tehama MPTS: `common1.mptsweb.com`
- Tehama Tyler: `https://recorder.tehama.ca.us`
- Tehama auction: tentative 2027 — lower urgency than Butte

**PROBLEM 3 — live_fetch_engine.py DOES NOT EXIST**
- The core on-demand live scraper is missing
- Without it, every county depends on whatever CSVs happen to exist — not a product, just a script folder
- This is the piece that turns the system into something you can sell: "pull any county, any time, live"

---

## HARD RULES — NON-NEGOTIABLE

1. **Never invent data.** Every APN, owner name, address must come from a live verified public source. Owner names require a source_url from a county/court domain + APN visible on that page.
2. **PowerShell syntax:** use `;` to chain commands, NOT `&&`
3. **No paid APIs, no keys required.** Public portals only.
4. **Isolated error sandboxing.** If one county fails, others must continue. Never let one county crash the whole run.
5. **Tag every output** with exact provenance: `LIVE_PORTAL_FETCH` vs `LOCAL_ROLL_INDEX` + ISO timestamp.
6. **If you can't verify it, label it `LEAD_UNVERIFIED`.** Never promote to `verified_owner_name` without a source URL.
7. **SQLite:** the column `values` is a reserved keyword — always quote it as `[values]` in queries.
8. **Do not say we did something we didn't.** Do not mark a dossier as verified if the data came from a static CSV with no live confirmation.

---

## TASK 1 — BUTTE RE-OFFER DOSSIERS (DO THIS FIRST — AUCTION AUG 7, 3 DAYS)

### Background
Butte's re-offer auction is Aug 7–10 on Bid4Assets. The note in the calendar says "104 active parcels ($5.05M total default)." We need verified dossiers for all 104 by Aug 6 EOD.

The July 29 package (`butte/delivery/butte_auction_2026-07-29/`) covered the *main* sale. This is a separate re-offer list — unsold parcels re-listed. The APN lists may overlap but are not identical.

### Step 1a — Fetch the live Butte re-offer parcel list

Try in this order using `requests` + `BeautifulSoup`:

1. **Butte Tax Collector page:**
   `https://www.buttecounty.net/treasurer-tax-collector/tax-sales`
   Look for a PDF or Excel link with "re-offer" or "2026" in the name.

2. **Bid4Assets search:**
   `https://www.bid4assets.com/search?countyID=&search=butte+county&statusID=all`
   Parse auction listings for Butte County. Each listing should have APN + minimum bid.

3. **Direct PDF attempt:**
   `https://www.buttecounty.net/Portals/0/PDF/TTC/2026ReofferTaxSale.pdf`

If PDF found: use `pdfplumber` to extract the parcel table.
If Bid4Assets HTML: parse listing cards for APN, address, opening bid.

Save raw results to: `data/counties/butte/auction_list_live_2026-08-07.csv`
Columns: `apn`, `apn_dash`, `address`, `minimum_bid`, `opening_bid`, `source_url`, `fetch_ts`

If you cannot get the live list after 3 attempts, fall back to `butte_test_75_ENRICHED.csv` (75 verified delinquent parcels from Tyler — real data) and tag all output as `DATA_SOURCE: FALLBACK_LOCAL` so Chuck knows.

### Step 1b — Enrich each APN via MPTS (live)

For each APN from Step 1a:
- Base URL: `https://common2.mptsweb.com/MBC/Butte/assessor/detail/{APN_NODASHES}/1/01-01-2026`
- Strip dashes from APN before inserting (e.g. `002-650-003-000` → `002650003000`)
- Parse owner name from HTML (look for `Owner Name` label in a table, or `AsrName` field)
- Parse assessed value (look for `Net Assessed Value`, `Total Assessed`, or `Land Value` + `Impr Value`)
- If MPTS 404/empty: mark `owner_source: MPTS_MISS` — do not invent a name
- Rate limit: 1 request per 1.5 seconds

Save to: `data/counties/butte/butte_auction_enriched.csv`
Columns: `apn`, `apn_dash`, `owner`, `assessed_value`, `address`, `minimum_bid`, `owner_source`, `source_url`, `fetch_ts`

### Step 1c — Generate prop intel dossiers

Use `report_builder.py` with the Butte enriched CSV.
Each dossier → `output/dashboard/butte_{APN}_prop_intel_dossier.md`

Tag every dossier with:
```
data_source: LIVE_PORTAL_FETCH   # or FALLBACK_LOCAL if fell back
fetch_timestamp: <ISO>
provenance_url: <actual URL fetched>
auction_date: 2026-08-07
auction_platform: Bid4Assets
```

Update `output/dashboard/dashboard_feed.json` with all Butte entries.

### Verification
```powershell
python -c "import glob; print('Butte dossiers:', len(glob.glob('output/dashboard/butte_*_prop_intel_dossier.md')))"
```
Target: ≥ 50 dossiers (ideally all 104)

---

## TASK 2 — BUILD live_fetch_engine.py

Create `C:\Users\chuck\Downloads\county_pipeline\live_fetch_engine.py`

This is the on-demand live scraper that makes the whole platform work without static CSV dependencies. Architecture:

```python
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
    county_cap = county.capitalize()
    url = f"https://{host}/MBC/{county_cap}/assessor/detail/{apn_clean}/1/01-01-2026"
    ts = datetime.now(timezone.utc).isoformat()
    result = {"apn": apn, "source_url": url, "fetch_ts": ts, "status": "MPTS_MISS", "owner": None, "assessed_value": None}
    try:
        resp = session.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 404:
            return result
        soup = BeautifulSoup(resp.text, "html.parser")
        # Parse owner: look for table rows where th/td label contains "Owner"
        owner = None
        assessed = None
        for row in soup.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                value = cells[1].get_text(strip=True)
                if "owner" in label and not owner:
                    owner = value
                if any(k in label for k in ["net assessed", "total assessed", "assessed value"]) and not assessed:
                    assessed = value
        result["owner"] = owner
        result["assessed_value"] = assessed
        result["status"] = "VERIFIED" if owner else "MPTS_MISS"
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
```

### Verification
```powershell
python live_fetch_engine.py --county humboldt --apn 305-073-053-000
```
Expected: `status: VERIFIED`, `owner: CASEY B A` (or similar), real source_url

---

## TASK 3 — FIX TEHAMA CIRCUIT BREAKER

### Root cause
Tehama CSVs have only 14 of 40,059 owners filled. Circuit breaker hits local CSV, finds nulls, halts correctly.

### Fix
1. Check what data exists:
   ```powershell
   python -c "import csv; rows=list(csv.DictReader(open('data/tehama/tehama_owner_enriched.csv', encoding='utf-8'))); print(len(rows), 'rows'); print(list(rows[0].keys()))"
   ```
2. For Tehama APNs with null owner, run MPTS live lookups using `live_fetch_engine.py`:
   ```powershell
   python live_fetch_engine.py --county tehama --apn-file data/tehama/tehama_signal_scan_full.csv --out output/tehama_mpts_fill.json
   ```
3. Merge live results back into `data/tehama/tehama_owner_enriched.csv`
4. Re-run circuit breaker to confirm it passes:
   ```powershell
   python integrity_circuit_breaker.py --county tehama
   ```
   Target: `null_ratio < 0.20` (currently 0.267 — need to fill ~4 more APNs per 15 checked)

---

## TASK 4 — COUNTY HEALTH MATRIX

After tasks 1–3, write/overwrite `output/county_health_matrix.json`:

```json
{
  "last_updated": "<ISO timestamp>",
  "counties": {
    "humboldt":  {"status": "HEALTHY",        "tax_deed_count": 207, "excess_proceeds_count": 30, "owner_fill_pct": 100, "auction_date": "2026-05-29-COMPLETE"},
    "butte":     {"status": "LIVE_FETCHED",   "auction_parcel_count": 104, "dossiers_generated": "<N>", "auction_date": "2026-08-07", "data_source": "LIVE_PORTAL_FETCH"},
    "fresno":    {"status": "HEALTHY",        "dossiers_generated": 50, "auction_date": "2026-09-10"},
    "tehama":    {"status": "CIRCUIT_PASS",   "owner_fill_pct": "<N after fix>", "auction_date": "2027-TENTATIVE"},
    "kern":      {"status": "CPRA_PENDING",   "auction_parcel_count": 940, "auction_date": "2026-09-14", "note": "Assessor roll via CPRA request pending"},
    "shasta":    {"status": "NEEDS_FILL",     "total_parcels": 94365, "owners_filled": 0}
  }
}
```

---

## KEY FILE LOCATIONS

| File | Purpose |
|---|---|
| `archive/tax_pipeline/butte_AUTHORITATIVE_master_index.csv` | 90,899 Butte APNs (apn_dash, address — no owners/flags) |
| `butte_test_75_ENRICHED.csv` | 75 verified delinquent Butte parcels — fallback if live fetch fails |
| `butte/delivery/butte_auction_2026-07-29/` | Full July delivery package (105 dossiers, sent to Jeff) |
| `data/california_tax_auction_calendar_2025_2027.csv` | 108-entry 58-county auction calendar |
| `data/tehama/tehama_signal_scan_full.csv` | Tehama parcel data (APN base) |
| `data/tehama/tehama_owner_enriched.csv` | Tehama with partial owner names |
| `data/counties/humboldt/tax_deed_parcels.csv` | COMPLETE — 207 rows, do not touch |
| `excess_proceeds/excess_proceeds_butte_2026.csv` | 433 Butte parcels, $3.34M, June 2027 deadline |
| `excess_proceeds/excess_proceeds_tehama_2025.csv` | 5.4MB — URGENT, some past 1-yr deadline |
| `output/dashboard/` | All generated dossiers and dashboard feed |
| `output/circuit_breaker_ALERT.json` | Tehama alert — must be cleared by Task 3 |
| `integrity_circuit_breaker.py` | Circuit breaker — run with county name arg |
| `report_builder.py` | Dossier generator |
| `owner_resolve.py` | 4-tier owner resolution cascade |
| `counties/butte.yaml` | Butte config: MPTS=common2, Tyler=recorder.buttecounty.net |
| `counties/tehama.yaml` | Tehama config: MPTS=common1, Tyler=recorder.tehama.ca.us |
| `tax_pipeline/recorder_config.py` | 4-county Tyler recorder adapter registry |
| `tax_pipeline/multi_county_engine.py` | Universal processor (`--county` flag) |
| `verification.sqlite` | Live 5-layer verification DB (1.7MB) |

---

## PROVEN ENDPOINTS — DO NOT BREAK THESE

| Endpoint | What | Notes |
|---|---|---|
| `common1.mptsweb.com/MBC/api/search/{county}/...` | MPTS tax + owner | Works for most counties |
| `common2.mptsweb.com/MBC/api/search/{county}/...` | Same | Butte + Shasta only |
| `recorder.buttecounty.net/web/search/DOCSEARCH481S1` | Butte Tyler recorder | Proven |
| `recorder.tehama.ca.us/web/search/DOCSEARCH4S1` | Tehama Tyler recorder | Proven |
| `apps.mptsweb.com/TaxBillv2/RollCatCS.aspx?CN={county}&Asmt={apn}` | Live tax bill | Used in stage4 |
| `services.arcgis.com/VYsrLd1WbPJ93eyz/.../Kern_County_Auction_List/FeatureServer/0/query` | Kern 940 parcels | Proven FATCO |

## DEAD ENDS — DO NOT RETRY

| Endpoint | Why |
|---|---|
| `kcttc.co.kern.ca.us/Payment/mainsearch.aspx` | CAPTCHA |
| `api.govease.com` | DNS does not resolve |
| `assessor.co.kern.ca.us` | 403 Forbidden |

---

## EXECUTION ORDER

1. **Task 1** — Butte is Aug 7. This is revenue. 3 days.
2. **Task 2** — `live_fetch_engine.py` is needed for Task 1 MPTS enrichment anyway. Build it first, then use it in Task 1b.
3. **Task 3** — Tehama circuit breaker. 2027 auction — lower urgency but needs clearing.
4. **Task 4** — Health matrix. Quick summary after everything else passes.

---

## AFTER ALL TASKS — ALSO NOTE FOR CHUCK

The following are pre-existing items flagged in `MASTER_AGENT_HANDOFF_2026-08-03.md` that are NOT in scope for this handoff but should not be lost:

- **Tehama excess proceeds** — `excess_proceeds/excess_proceeds_tehama_2025.csv` (5.4MB) has some 2025 deeds already past the 1-year escheat window. Skip trace + letter campaign needed ASAP.
- **Butte excess proceeds** — 433 parcels, $3.34M, outreach list ready but letters not sent yet. Deadline June 2027.
- **Kern** — 940 scored parcels ready. CPRA assessor roll request pending. Auction Sept 14.
- **Fresno** — Monitor daily (`python fresno/fresno_daily_monitor.py`). List drops ~Aug 10. Auction Sept 10–11.
- **stage7_recorder_enrich.py** — Hardcoded, ignores `recorder_config.py`. Multi-county recorder flow is broken at Stage 7. Fix is documented in MASTER_AGENT_HANDOFF_2026-08-03.md lines 133–191.
- **Gemini API key** — Hardcoded in `tax_pipeline/butte_e2e_test.py:3` and `tax_pipeline/butte_stage3_test.py:3`. Replace with `os.environ.get("GEMINI_API_KEY")` and rotate the key.
- **Dashboard.py** — Crashes on launch. Missing `northern_ca_MASTER_merged.csv`. Restore file or update default path.

---

*Handoff written: 2026-08-04 17:49 PDT*
*Previous master: `MASTER_AGENT_HANDOFF_2026-08-03.md`*
*Prior agent session: `AGENT_HANDOFF_2026-08-03_OWNER_RESOLVE.md`*
