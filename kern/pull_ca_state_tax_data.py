"""
Pull California State Property Tax Raw Data from data.ca.gov
Dataset: "Property Tax Raw Data for Fiscal Years 2019-20 to 2025-26"
This is the SCO (State Controller's Office) dataset — parcel-level tax data
published under California R&TC requirements. Free. Public. No API key needed.
"""
import os, requests, json
import pandas as pd
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
BASE = r"C:\Users\chuck\Downloads\county_pipeline\kern"

# Step 1: Get dataset metadata
print("=== CALIFORNIA STATE PROPERTY TAX RAW DATA ===")
datasets = [
    ("property-tax-raw-data-for-fiscal-years-2019-20-to-2025-26", "2019-2026"),
    ("property-tax-raw-data-for-fiscal-years-2002-03-to-2018-19", "2002-2018"),
    ("property-tax-levies", "Levies"),
    ("parcelization-file-geodatabase", "Parcelization GDB"),
]

for slug, label in datasets:
    url = f"https://data.ca.gov/api/3/action/package_show?id={slug}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        d = r.json()
        result = d.get("result", {})
        print(f"\n--- {label} ---")
        print(f"  Title: {result.get('title')}")
        print(f"  Notes: {str(result.get('notes',''))[:200]}")
        resources = result.get("resources", [])
        print(f"  Resources: {len(resources)}")
        for res in resources:
            print(f"    Format: {res.get('format')} | Name: {res.get('name')} | URL: {res.get('url','')[:100]}")
    except Exception as e:
        print(f"  {slug} -> ERROR: {e}")

# Step 2: Try to directly download the raw data CSV
print("\n=== ATTEMPTING DIRECT DOWNLOAD OF CA PROPERTY TAX RAW DATA ===")
download_urls = [
    "https://data.ca.gov/dataset/property-tax-raw-data-for-fiscal-years-2019-20-to-2025-26/resource/",
    "https://data.ca.gov/datastore/dump/property-tax-raw-data",
]

# Try the CKAN datastore API
ckan_urls = [
    "https://data.ca.gov/api/3/action/datastore_search?resource_id=property-tax-raw-data-for-fiscal-years-2019-20-to-2025-26&q=kern&limit=100",
    "https://data.ca.gov/api/3/action/resource_search?query=name:kern+property+tax",
]
for url in ckan_urls:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        print(f"  {url[:80]} -> {r.status_code}")
        if r.status_code == 200:
            d = r.json()
            print(f"  Keys: {list(d.keys())}")
            result = d.get("result", {})
            print(f"  Result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
    except Exception as e:
        print(f"  ERROR: {e}")

# Step 3: Try the Parcelization GDB dataset
print("\n=== PARCELIZATION FILE GEODATABASE ===")
r = requests.get("https://data.ca.gov/api/3/action/package_show?id=parcelization-file-geodatabase", 
                 headers=HEADERS, timeout=10)
result = r.json().get("result", {})
for res in result.get("resources", []):
    print(f"  Format: {res.get('format')} | Name: {res.get('name')}")
    print(f"  URL: {res.get('url','')}")
    # Try to fetch if it's a CSV or JSON
    res_url = res.get("url","")
    if res_url and any(res_url.lower().endswith(ext) for ext in [".csv",".json",".geojson"]):
        try:
            tr = requests.get(res_url, headers=HEADERS, timeout=10, stream=True)
            print(f"  Download status: {tr.status_code} | Content-Length: {tr.headers.get('content-length','unknown')}")
        except Exception as e:
            print(f"  Download error: {e}")
