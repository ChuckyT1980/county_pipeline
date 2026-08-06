"""
Deep Kern County Endpoint Reconnaissance
1. Parses https://maps.kerncounty.com/arcgis/rest/services for parcel/assessor layer
2. Parses https://www.kcttc.co.kern.ca.us/ for tax bill lookup form endpoints
3. Parses https://www.govease.com/auctions for Kern County auction links
4. Searches Kern County Open Data / ArcGIS Online for APN layer
"""
import os
import re
import sys
import json
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/json,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

def deep_probe_kcttc():
    print("=== [1] KCTTC TAX COLLECTOR DEEP RECON ===")
    url = "https://www.kcttc.co.kern.ca.us/"
    r = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(r.text, "html.parser")
    
    forms = soup.find_all("form")
    print(f"Found {len(forms)} HTML forms on KCTTC home page:")
    for idx, f in enumerate(forms):
        print(f" Form #{idx+1}: action='{f.get('action')}', method='{f.get('method')}'")
        inputs = f.find_all("input")
        for i in inputs:
            print(f"   Input: name='{i.get('name')}', type='{i.get('type')}', value='{i.get('value')}'")

    links = soup.find_all("a", href=True)
    print(f"\nFound {len(links)} links on KCTTC home page. Tax/Property links:")
    for l in links:
        href = l["href"]
        text = l.text.strip()
        if any(k in href.lower() or k in text.lower() for k in ["tax", "bill", "pay", "search", "parcel", "apn", "auction", "sale"]):
            print(f" Link: '{text}' -> {href}")

def deep_probe_gis():
    print("\n=== [2] ARCGIS / GIS DEEP RECON ===")
    url = "https://maps.kerncounty.com/arcgis/rest/services?f=json"
    r = requests.get(url, headers=HEADERS)
    if r.status_code == 200:
        data = r.json()
        print("Folders:", data.get("folders", []))
        print("Services:", [s["name"] for s in data.get("services", [])])
        
        # Check folders
        for folder in data.get("folders", []):
            furl = f"https://maps.kerncounty.com/arcgis/rest/services/{folder}?f=json"
            fr = requests.get(furl, headers=HEADERS)
            if fr.status_code == 200:
                fdata = fr.json()
                print(f" Folder '{folder}' services:", [s["name"] for s in fdata.get("services", [])])

def deep_probe_govease():
    print("\n=== [3] GOVEASE DEEP RECON ===")
    url = "https://www.govease.com/auctions"
    r = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text()
    
    # Search for Kern or California auctions
    links = soup.find_all("a", href=True)
    kern_links = [l for l in links if "kern" in l["href"].lower() or "kern" in l.text.lower()]
    print(f"GovEase Kern links: {len(kern_links)}")
    for l in kern_links:
        print(f"  Link: '{l.text.strip()}' -> {l['href']}")

def main():
    deep_probe_kcttc()
    deep_probe_gis()
    deep_probe_govease()

if __name__ == "__main__":
    main()
