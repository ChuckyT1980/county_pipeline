"""
Parse the ArcGIS Hub response for Fresno County parcel data
and try alternative Fresno data sources
"""
import requests, json
import pandas as pd

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}

# Parse ArcGIS Hub results
print("=== ARCGIS HUB FRESNO PARCEL DATASETS ===")
r = requests.get("https://hub.arcgis.com/api/v3/datasets",
    params={"q": "fresno county parcel tax", "filter[type]": "Feature Layer", "page[size]": 20},
    headers=HEADERS, timeout=15)
data = r.json()
datasets = data.get("data", [])
print(f"Datasets found: {len(datasets)}")
for d in datasets:
    attrs = d.get("attributes", {})
    name = attrs.get("name","")
    owner = attrs.get("ownerName","")
    url = attrs.get("url","") or attrs.get("accessInformation","")
    layer_url = attrs.get("layer",{}).get("url","") if isinstance(attrs.get("layer"),dict) else ""
    slug = attrs.get("slug","")
    print(f"\n  Name:  {name}")
    print(f"  Owner: {owner}")
    print(f"  Slug:  {slug}")
    print(f"  URL:   {url or layer_url}")

# Try to find actual Fresno FeatureServer from hub results
print("\n=== CHECKING FRESNO HUB FEATURE SERVICES ===")
for d in datasets:
    attrs = d.get("attributes", {})
    name = attrs.get("name","").lower()
    if "fresno" in name or "frn" in name:
        url = attrs.get("url","")
        if url:
            print(f"Trying: {url}")
            try:
                tr = requests.get(f"{url}?f=json", headers=HEADERS, timeout=8)
                if tr.status_code == 200:
                    td = tr.json()
                    print(f"  Fields: {[f['name'] for f in td.get('fields',[])[:8]]}")
            except Exception as e:
                print(f"  Error: {e}")

# Try Fresno County direct APN lookup via property search
print("\n=== FRESNO COUNTY PROPERTY SEARCH (DIRECT PATTERNS) ===")
urls = [
    "https://www.co.fresno.ca.us/departments/treasurer-tax-collector/property-tax",
    "https://eproperty.co.fresno.ca.us/",
    "https://myfresnocounty.co.fresno.ca.us/",
    "https://aca.co.fresno.ca.us/",
    "https://www.co.fresno.ca.us/",
]
for url in urls:
    try:
        r = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
        print(f"  {url} -> {r.status_code} ({len(r.text)} bytes) | Final URL: {r.url[:80]}")
    except Exception as e:
        print(f"  {url} -> ERROR: {e}")

# Try ArcGIS search specifically for FATCO/FirstAmerican Fresno
print("\n=== FATCO ARCGIS SEARCH (BROADER) ===")
for q in ["afalkner Fresno", "FATCO Fresno auction", "FirstAmerican Fresno tax sale"]:
    r = requests.get("https://www.arcgis.com/sharing/rest/search",
        params={"q": q, "f": "json", "num": 5, "owner": "afalkner_FATCO"},
        headers=HEADERS, timeout=10)
    results = r.json().get("results", [])
    print(f"  Query '{q}': {len(results)} results")
    for item in results:
        print(f"    {item.get('title')} | {item.get('url')}")

# List ALL FATCO items to see what counties they cover
print("\n=== ALL FATCO AUCTION LISTS PUBLISHED ===")
r = requests.get("https://www.arcgis.com/sharing/rest/search",
    params={"q": "Auction List", "f": "json", "num": 50, "owner": "afalkner_FATCO"},
    headers=HEADERS, timeout=10)
results = r.json().get("results", [])
print(f"Total FATCO auction lists found: {len(results)}")
for item in results:
    print(f"  {item.get('title')} | {item.get('url','')[:80]}")
