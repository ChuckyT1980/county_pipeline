"""
Kern County Work Audit Script
Checks what was actually proven vs claimed.
Runs live probes against every endpoint listed in HANDOFF_KERN_ENDPOINT_RECON.md
"""
import requests
from bs4 import BeautifulSoup
import json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}

def check(label, url, check_fn=None):
    print(f"\n--- {label} ---")
    print(f"URL: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        print(f"Status: {r.status_code}  Bytes: {len(r.text)}")
        if check_fn and r.status_code == 200:
            check_fn(r)
        return r
    except Exception as e:
        print(f"ERROR: {e}")
        return None

def parse_kcttc_search(r):
    soup = BeautifulSoup(r.text, "html.parser")
    forms = soup.find_all("form")
    print(f"  Forms on page: {len(forms)}")
    for f in forms:
        print(f"  Form action={f.get('action')} method={f.get('method')}")
        for inp in f.find_all(["input","select"]):
            print(f"    {inp.name}: name={inp.get('name')} type={inp.get('type')} id={inp.get('id')}")

def parse_kcttc_taxsale(r):
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text()
    # Look for auction dates, parcel counts, GovEase links
    for line in text.split("\n"):
        line = line.strip()
        if any(k in line.lower() for k in ["sept", "2026", "auction", "parcel", "govease", "notice"]):
            if len(line) > 5:
                print(f"  FOUND: {line[:120]}")

def parse_arcgis_parcel_layer(r):
    try:
        data = r.json()
        print(f"  Layer name: {data.get('name')}")
        print(f"  Fields: {[f.get('name') for f in data.get('fields', [])][:10]}")
        print(f"  Max record count: {data.get('maxRecordCount')}")
        print(f"  Geometry type: {data.get('geometryType')}")
    except Exception as e:
        print(f"  Could not parse JSON: {e}")

def parse_govease(r):
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text()
    for line in text.split("\n"):
        line = line.strip()
        if "kern" in line.lower() and len(line) > 5:
            print(f"  GOVEASE KERN MENTION: {line[:120]}")
    links = soup.find_all("a", href=True)
    kern_links = [l for l in links if "kern" in l.get("href","").lower() or "kern" in l.text.lower()]
    print(f"  Kern-specific links on GovEase: {len(kern_links)}")
    for l in kern_links[:10]:
        print(f"    {l.text.strip()} -> {l['href']}")

def try_real_apn_taxbill(apn):
    """Try to pull a real tax bill for an APN from KCTTC."""
    url = f"https://www.kcttc.co.kern.ca.us/Payment/mainsearch.aspx"
    print(f"\n--- ATTEMPTING REAL APN LOOKUP: {apn} ---")
    # First get the search page to grab ViewState
    s = requests.Session()
    r1 = s.get(url, headers=HEADERS, timeout=10)
    print(f"  Search page status: {r1.status_code}")
    soup = BeautifulSoup(r1.text, "html.parser")
    vs = soup.find("input", {"id": "__VIEWSTATE"})
    ev = soup.find("input", {"id": "__EVENTVALIDATION"})
    vsgen = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})
    if vs:
        print(f"  ViewState found: YES (len={len(vs.get('value',''))})")
        # Post the APN search
        payload = {
            "__VIEWSTATE": vs.get("value",""),
            "__EVENTVALIDATION": ev.get("value","") if ev else "",
            "__VIEWSTATEGENERATOR": vsgen.get("value","") if vsgen else "",
            "txtAPN": apn,
            "btnSearch": "Search"
        }
        # Find actual submit button name
        btn = soup.find("input", {"type": "submit"})
        if btn:
            payload[btn.get("name","btnSearch")] = btn.get("value","Search")
            print(f"  Submit button name: {btn.get('name')}, value: {btn.get('value')}")
        r2 = s.post(url, data=payload, headers=HEADERS, timeout=10)
        print(f"  POST response status: {r2.status_code}  Bytes: {len(r2.text)}")
        soup2 = BeautifulSoup(r2.text, "html.parser")
        text = soup2.get_text()
        for line in text.split("\n"):
            line = line.strip()
            if any(k in line.lower() for k in ["apn","owner","amount","balance","delinquent","situs","address","parcel"]):
                if len(line) > 5:
                    print(f"  RESULT: {line[:120]}")
    else:
        print("  ViewState NOT found - page may be fully JavaScript rendered or session-based")
        print("  First 500 chars of page:")
        print(r1.text[:500])

if __name__ == "__main__":
    print("=" * 60)
    print("KERN COUNTY WORK AUDIT - LIVE ENDPOINT VERIFICATION")
    print("=" * 60)

    # 1. KCTTC main search page
    check("KCTTC MAIN SEARCH", 
          "https://www.kcttc.co.kern.ca.us/Payment/mainsearch.aspx",
          parse_kcttc_search)

    # 2. KCTTC Tax Sale Info page
    check("KCTTC TAX SALE INFO PAGE",
          "https://www.kcttc.co.kern.ca.us/index.cfm?fuseaction=kcttcinternet.showGeneralTaxSaleInfo",
          parse_kcttc_taxsale)

    # 3. GovEase auction registration for Kern (ID 1348 was found in the KCTTC links)
    check("GOVEASE KERN AUCTION REGISTRATION",
          "https://liveauctions.govease.com/PublicPortal/RegistrationDetail?AuctionID=1348&Edit=False/",
          parse_govease)

    # 4. GovEase main auctions list
    check("GOVEASE AUCTIONS LIST",
          "https://www.govease.com/auctions",
          parse_govease)

    # 5. Kern ArcGIS Parcel layer
    check("KERN ARCGIS PARCEL LAYER 0",
          "https://maps.kerncounty.com/arcgis/rest/services/Kern_AGS_Parcels/MapServer/0?f=json",
          parse_arcgis_parcel_layer)

    # 6. Try a real APN against the KCTTC search
    try_real_apn_taxbill("001-100-01")

    print("\n" + "=" * 60)
    print("AUDIT COMPLETE")
    print("=" * 60)
