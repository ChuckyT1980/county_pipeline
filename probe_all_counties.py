"""
Systematically probe every CA county for parcel data availability.

For each county, tests:
  1. MPTS tax bill endpoint (Butte/Tehama pattern)
  2. Common ArcGIS FeatureServer patterns for parcels
  3. County TTC / Assessor web page (checks for Akamai gating)
  4. Bid4Assets / GovEase / Realauction / MyTaxSale auction platform

Outputs: ca_county_probe_results.csv with what works, what doesn't, what's blocked.
"""
import csv
import time
import requests
from pathlib import Path

OUT_CSV = Path(__file__).parent / "ca_county_probe_results.csv"

# All 58 CA counties
COUNTIES = [
    "alameda", "alpine", "amador", "butte", "calaveras", "colusa", "contra costa",
    "del norte", "el dorado", "fresno", "glenn", "humboldt", "imperial", "inyo",
    "kern", "kings", "lake", "lassen", "los angeles", "madera", "marin", "mariposa",
    "mendocino", "merced", "modoc", "mono", "monterey", "napa", "nevada", "orange",
    "placer", "plumas", "riverside", "sacramento", "san benito", "san bernardino",
    "san diego", "san francisco", "san joaquin", "san luis obispo", "san mateo",
    "santa barbara", "santa clara", "santa cruz", "shasta", "sierra", "siskiyou",
    "solano", "sonoma", "stanislaus", "sutter", "tehama", "trinity", "tulare",
    "tuolumne", "ventura", "yolo", "yuba",
]

MPTS_HOSTS = ["common1.mptsweb.com", "common2.mptsweb.com"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
HEADERS = {"User-Agent": UA}
TIMEOUT = 8


def _get(url, timeout=TIMEOUT):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        return r
    except requests.RequestException:
        return None


def probe_mpts(county):
    """Test if county is on MPTS platform."""
    slug = county.replace(" ", "")
    for host in MPTS_HOSTS:
        r = _get(f"https://{host}/mbc/{slug}/tax/search", timeout=5)
        if r and r.status_code == 200 and len(r.text) > 2000:
            return {"mpts_host": host, "mpts_ok": True}
        r = _get(f"https://{host}/mbap/{slug}/asr", timeout=5)
        if r and r.status_code == 200 and len(r.text) > 2000:
            return {"mpts_host": host, "mpts_ok": True}
    return {"mpts_host": "", "mpts_ok": False}


def probe_arcgis(county):
    """Common ArcGIS FeatureServer patterns per county."""
    slug = county.replace(" ", "").lower()
    dashslug = county.replace(" ", "-").lower()
    candidates = [
        f"https://gis.{slug}county.ca.gov/arcgis/rest/services",
        f"https://gis.{slug}.ca.gov/arcgis/rest/services",
        f"https://maps.{slug}.ca.gov/arcgis/rest/services",
        f"https://maps.co.{slug}.ca.us/arcgis/rest/services",
        f"https://gisportal.co.{slug}.ca.us/portal/sharing/rest/portals/self?f=json",
        f"https://gis.co.{slug}.ca.us/arcgis/rest/services",
        f"https://services.arcgis.com/{slug}",  # generic — will 404 but tests hostname
    ]
    for url in candidates:
        r = _get(url + ("?f=json" if "?f=json" not in url else ""), timeout=6)
        if r and r.status_code == 200 and ("services" in r.text.lower() or "portal" in r.text.lower()):
            return {"arcgis_ok": True, "arcgis_host": url.split("/arcgis")[0] if "/arcgis" in url else url}
    return {"arcgis_ok": False, "arcgis_host": ""}


def probe_county_site(county):
    """Test main county government site accessibility (Akamai gating check)."""
    slug = county.replace(" ", "")
    dashslug = county.replace(" ", "-")
    candidates = [
        f"https://www.{slug}county.ca.gov/",
        f"https://www.co.{slug}.ca.us/",
        f"https://www.{slug}countyca.gov/",
        f"https://{slug}county.gov/",
    ]
    for url in candidates:
        r = _get(url, timeout=6)
        if r is None:
            continue
        # Check for Akamai block (Access Denied)
        if r.status_code == 403 and "access denied" in r.text.lower():
            return {"county_site": url, "county_ok": False, "county_blocked": "akamai"}
        if r.status_code == 200 and len(r.text) > 2000:
            return {"county_site": url, "county_ok": True, "county_blocked": ""}
    return {"county_site": "", "county_ok": False, "county_blocked": "unreachable"}


def probe_bid4assets(county):
    """Check if county has Bid4Assets presence."""
    slug = county.replace(" ", "")
    r = _get(f"https://www.bid4assets.com/{slug}", timeout=6)
    if r and r.status_code == 200 and slug.lower() in r.text.lower():
        return {"bid4assets": True}
    return {"bid4assets": False}


def probe_county(county):
    print(f"  Probing {county}...", end=" ", flush=True)
    result = {"county": county}
    result.update(probe_mpts(county))
    result.update(probe_arcgis(county))
    result.update(probe_county_site(county))
    result.update(probe_bid4assets(county))

    # Summarize what's lacking
    lacking = []
    if not result["mpts_ok"]:
        lacking.append("no_mpts")
    if not result["arcgis_ok"]:
        lacking.append("no_public_arcgis_found")
    if result["county_blocked"] == "akamai":
        lacking.append("county_site_akamai_blocked")
    if not result["bid4assets"]:
        lacking.append("no_bid4assets")
    result["lacking"] = ",".join(lacking) if lacking else "none"

    # Access tier
    tiers = []
    if result["mpts_ok"]: tiers.append("MPTS")
    if result["arcgis_ok"]: tiers.append("ArcGIS")
    if result["county_ok"]: tiers.append("website")
    if result["bid4assets"]: tiers.append("Bid4Assets")
    result["access_tier"] = "+".join(tiers) if tiers else "none"

    print(f"[{result['access_tier'] or 'none'}]")
    return result


def main():
    results = []
    for county in COUNTIES:
        r = probe_county(county)
        results.append(r)
        time.sleep(0.3)

    # Write CSV
    keys = ["county", "access_tier", "mpts_host", "mpts_ok",
            "arcgis_ok", "arcgis_host",
            "county_site", "county_ok", "county_blocked",
            "bid4assets", "lacking"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=keys)
        w.writeheader()
        for r in results:
            row = {k: r.get(k, "") for k in keys}
            w.writerow(row)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"Probed {len(results)} counties. Results saved to {OUT_CSV.name}")
    print(f"{'=' * 60}")
    tier_counts = {}
    for r in results:
        t = r.get("access_tier") or "none"
        tier_counts[t] = tier_counts.get(t, 0) + 1
    print("\nCounties by access tier:")
    for t, c in sorted(tier_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:40} {c}")

    print(f"\nMPTS counties found: {sum(1 for r in results if r['mpts_ok'])}")
    print(f"Counties with detectable public ArcGIS: {sum(1 for r in results if r['arcgis_ok'])}")
    print(f"Counties on Bid4Assets: {sum(1 for r in results if r['bid4assets'])}")
    print(f"Counties Akamai-blocked: {sum(1 for r in results if r.get('county_blocked') == 'akamai')}")


if __name__ == "__main__":
    main()
