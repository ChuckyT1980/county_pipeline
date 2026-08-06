"""
Kern County Assessor Verification - Top 10 Priority Parcels
Tries every available public route to get real assessed values:
1. Check if the full FATCO raw pull has assessor data for these APNs
2. Try Kern County Assessor property search portal
3. Try ATTOM / public property data sources
4. Try Zillow/Redfin API endpoints for market value cross-check
5. Try Kern County GIS geocoder to find parcel record links
"""
import os, re, requests, json
import pandas as pd
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
BASE = r"C:\Users\chuck\Downloads\county_pipeline\kern"

# Load top 10 from scored call sheet
df_scored = pd.read_csv(os.path.join(BASE, "kern_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"))
top10 = df_scored.head(10)[["Parcel_Number", "Owner", "Parcel_Location",
                              "min_bid", "net_assessed_value", "nav_source",
                              "max_bid_70pct", "gross_equity_at_70", "priority_score"]].copy()

print("=== TOP 10 KERN PARCELS TO VERIFY ===")
print(top10.to_string())
print()

# ─── SOURCE 1: Check full FATCO raw pull for assessor data ────────
print("=== [1] CHECKING FATCO RAW PULL FOR REAL ASSESSOR VALUES ===")
df_raw = pd.read_csv(os.path.join(BASE, "kern_REAL_auction_list_fatco.csv"), low_memory=False)
top10_apns = top10["Parcel_Number"].tolist()

for apn in top10_apns:
    match = df_raw[df_raw["Parcel_Number"] == apn]
    if not match.empty:
        atv = match["ASSESSED_TOTAL_VALUE"].values[0]
        alv = match["ASSESSED_LAND_VALUE"].values[0]
        aiv = match["ASSESSED_IMPROVEMENT_VALUE"].values[0]
        mtv = match["MARKET_TOTAL_VALUE"].values[0] if "MARKET_TOTAL_VALUE" in match.columns else None
        print(f"  {apn}: ASSESSED_TOTAL={atv} | LAND={alv} | IMP={aiv} | MARKET={mtv}")
    else:
        print(f"  {apn}: NOT IN FATCO RAW")

# ─── SOURCE 2: Kern County Assessor portal (try alternate URLs) ───
print("\n=== [2] KERN ASSESSOR PORTAL DIRECT APN LOOKUP ATTEMPTS ===")
assessor_urls = [
    "https://assessor.co.kern.ca.us/assessor/property-search",
    "https://www.kernassessor.net/",
    "https://kern.propertytaxresearch.com/",
    "https://www.propertyshark.com/mason/api/report/",
]
for url in assessor_urls:
    try:
        r = requests.get(url, headers=HEADERS, timeout=6, verify=False)
        print(f"  {url} -> {r.status_code} ({len(r.text)} bytes)")
    except Exception as e:
        print(f"  {url} -> ERROR: {e}")

# ─── SOURCE 3: Try free property data APIs with a sample APN ──────
print("\n=== [3] PUBLIC PROPERTY DATA API PROBES ===")

# Test APN - first top parcel
sample_apn = top10_apns[0]  # 019-053-09-00-9
sample_situs = str(top10[top10["Parcel_Number"] == sample_apn]["Parcel_Location"].values[0])
print(f"Testing with APN: {sample_apn}  Situs: {sample_situs}")

# Try ATTOM Data (free tier)
attom_urls = [
    f"https://api.attomdata.com/propertyapi/v1.0.0/property/detail?APN={sample_apn.replace('-','')}&CountyFIPS=06029",
    f"https://api.attomdata.com/propertyapi/v1.0.0/property/basicprofile?APN={sample_apn}&state=CA&county=Kern",
]
for url in attom_urls:
    try:
        r = requests.get(url, headers={**HEADERS, "apikey": "demo"}, timeout=6)
        print(f"  ATTOM: {url[:80]} -> {r.status_code}")
        if r.status_code == 200:
            print(f"  Response: {r.text[:300]}")
    except Exception as e:
        print(f"  ATTOM error: {e}")

# Try Regrid (free parcel data)
regrid_urls = [
    f"https://app.regrid.com/api/v1/parcels/apn?apn={sample_apn}&county=kern&state=ca&token=demo",
    f"https://regrid.com/api/v1/parcel.json?apn={sample_apn}&state=ca&county=kern",
]
for url in regrid_urls:
    try:
        r = requests.get(url, headers=HEADERS, timeout=6)
        print(f"  Regrid: {url[:80]} -> {r.status_code} ({len(r.text)} bytes)")
        if r.status_code == 200:
            print(f"  Response: {r.text[:300]}")
    except Exception as e:
        print(f"  Regrid error: {e}")

# Try OpenStreetMap Nominatim for address geocoding
nom_url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(sample_situs + ' Kern County CA')}&format=json&limit=1"
try:
    r = requests.get(nom_url, headers={**HEADERS, "Referer": "https://logicflowsystems.io"}, timeout=8)
    print(f"\n  Nominatim: {r.status_code}")
    if r.status_code == 200 and r.json():
        loc = r.json()[0]
        print(f"  Lat: {loc.get('lat')}  Lon: {loc.get('lon')}  Display: {loc.get('display_name')}")
except Exception as e:
    print(f"  Nominatim error: {e}")

# ─── SOURCE 4: Kern County GIS geocoder ───────────────────────────
print("\n=== [4] KERN COUNTY GIS GEOCODER ===")
geocode_url = "https://maps.kerncounty.com/arcgis/rest/services/Public/ITS_Composite_Locator_GOGov/GeocodeServer/findAddressCandidates"
params = {
    "Single Line Input": sample_situs + ", Kern County, CA",
    "f": "json",
    "outFields": "*",
    "maxLocations": 1
}
try:
    r = requests.get(geocode_url, params=params, headers=HEADERS, timeout=8)
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        candidates = data.get("candidates", [])
        print(f"  Candidates: {len(candidates)}")
        if candidates:
            c = candidates[0]
            print(f"  Match: {c.get('address')} | Score: {c.get('score')} | Attrs: {c.get('attributes')}")
except Exception as e:
    print(f"  Error: {e}")

print("\n=== AUDIT COMPLETE ===")
