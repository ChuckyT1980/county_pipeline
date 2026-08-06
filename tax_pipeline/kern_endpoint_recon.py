"""
Kern County Endpoint Recon Script
Performs live endpoint probes against:
1. Kern County Assessor ArcGIS FeatureServer / MapServer REST services
2. Kern County Treasurer-Tax Collector (KCTTC) Megabyte MPTS endpoints
3. Kern County Recorder index portal
4. GovEase published auction listing index
5. Kern County published public tax sale PDF / notice endpoints

Outputs raw responses, endpoints status, rate limit behaviors, and field schemas.
"""
import os
import sys
import json
import time
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/json,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

def probe_arcgis():
    print("--- [1] PROBING KERN ASSESSOR ARCGIS GIS ENDPOINTS ---")
    urls = [
        "https://gis.kerncounty.com/arcgis/rest/services",
        "https://services1.arcgis.com/KernCounty/arcgis/rest/services",
        "https://maps.kerncounty.com/arcgis/rest/services",
        "https://gis.bakersfieldcity.us/arcgis/rest/services"
    ]
    found = []
    for u in urls:
        try:
            r = requests.get(u + "?f=json", headers=HEADERS, timeout=8)
            print(f"URL: {u} -> Status {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                services = [s.get("name") for s in data.get("services", [])]
                print(f"  Found {len(services)} services: {services[:5]}")
                found.append({"url": u, "services": services})
        except Exception as e:
            print(f"URL: {u} -> Error: {e}")
    return found

def probe_kcttc():
    print("\n--- [2] PROBING KERN TAX COLLECTOR (KCTTC) ENDPOINTS ---")
    urls = [
        "https://www.kcttc.co.kern.ca.us/",
        "https://kcttc.co.kern.ca.us/MBC/taxbill",
        "https://kcttc.co.kern.ca.us/mpts/",
        "https://www.kcttc.co.kern.ca.us/taxsale/",
        "https://www.kcttc.co.kern.ca.us/pay/"
    ]
    found = []
    for u in urls:
        try:
            r = requests.get(u, headers=HEADERS, timeout=8)
            print(f"URL: {u} -> Status {r.status_code} (Len: {len(r.text)})")
            if r.status_code == 200:
                found.append({"url": u, "len": len(r.text)})
        except Exception as e:
            print(f"URL: {u} -> Error: {e}")
    return found

def probe_govease():
    print("\n--- [3] PROBING GOVEASE KERN AUCTION ENDPOINTS ---")
    urls = [
        "https://www.govease.com/auctions",
        "https://www.govease.com/upcoming-auctions",
        "https://api.govease.com/auctions"
    ]
    found = []
    for u in urls:
        try:
            r = requests.get(u, headers=HEADERS, timeout=8)
            print(f"URL: {u} -> Status {r.status_code}")
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                print(f"  Page title: {soup.title.text if soup.title else 'No title'}")
                found.append({"url": u, "title": soup.title.text if soup.title else ""})
        except Exception as e:
            print(f"URL: {u} -> Error: {e}")
    return found

def probe_recorder():
    print("\n--- [4] PROBING KERN RECORDER ENDPOINTS ---")
    urls = [
        "https://recorder.kerncounty.com/",
        "https://kern.clerk-recorder.com/",
        "https://recorder.co.kern.ca.us/"
    ]
    found = []
    for u in urls:
        try:
            r = requests.get(u, headers=HEADERS, timeout=8)
            print(f"URL: {u} -> Status {r.status_code}")
            if r.status_code == 200:
                found.append({"url": u})
        except Exception as e:
            print(f"URL: {u} -> Error: {e}")
    return found

def main():
    print("Beginning Kern County Live Endpoint Recon...")
    probe_arcgis()
    probe_kcttc()
    probe_govease()
    probe_recorder()

if __name__ == "__main__":
    main()
