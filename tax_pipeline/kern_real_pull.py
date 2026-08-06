"""
Pull real parcel data from the two proven live sources:
1. First American Title / FATCO ArcGIS FeatureServer - Kern County Auction List (published real data)
2. KCTTC showTaxSaleList / showDefaultedProperty pages - parse real content
"""
import os, re, json, requests
from bs4 import BeautifulSoup
import pandas as pd

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
BASE = r"C:\Users\chuck\Downloads\county_pipeline\kern"
os.makedirs(BASE, exist_ok=True)

# ─────────────────────────────────────────────
# SOURCE 1: FATCO ArcGIS Feature Services (real auction lists published by First American Title)
# ─────────────────────────────────────────────
def pull_fatco_auction_list():
    print("\n=== PULLING FATCO KERN COUNTY AUCTION FEATURE SERVICE ===")
    base_urls = [
        "https://services.arcgis.com/VYsrLd1WbPJ93eyz/arcgis/rest/services/Kern_County_Auction_List/FeatureServer/0",
        "https://services.arcgis.com/VYsrLd1WbPJ93eyz/arcgis/rest/services/Kern_County_Auction_List_March_2024/FeatureServer/0",
    ]
    all_records = []
    for base in base_urls:
        # Get layer info first
        info_r = requests.get(f"{base}?f=json", headers=HEADERS, timeout=10)
        if info_r.status_code == 200:
            info = info_r.json()
            print(f"\nLayer: {info.get('name')}")
            fields = [f['name'] for f in info.get('fields', [])]
            print(f"Fields ({len(fields)}): {fields}")
            print(f"Max records: {info.get('maxRecordCount')}")

            # Pull actual records
            query_url = f"{base}/query"
            params = {
                "where": "1=1",
                "outFields": "*",
                "f": "json",
                "resultRecordCount": 1000,
                "returnGeometry": "false"
            }
            q = requests.get(query_url, params=params, headers=HEADERS, timeout=15)
            print(f"Query status: {q.status_code}  Bytes: {len(q.text)}")
            if q.status_code == 200:
                data = q.json()
                features = data.get("features", [])
                print(f"Records returned: {len(features)}")
                if features:
                    print(f"Sample record: {json.dumps(features[0], indent=2)[:600]}")
                    for f in features:
                        all_records.append(f.get("attributes", {}))
        else:
            print(f"  {base} -> {info_r.status_code}")
    return all_records

# ─────────────────────────────────────────────
# SOURCE 2: KCTTC showTaxSaleList pages
# ─────────────────────────────────────────────
def pull_kcttc_taxsale_pages():
    print("\n=== PULLING KCTTC TAX SALE / DEFAULTED PROPERTY PAGES ===")
    urls = [
        ("showTaxSaleList", "https://www.kcttc.co.kern.ca.us/index.cfm?fuseaction=kcttcinternet.showTaxSaleList"),
        ("showDefaultedProperty", "https://www.kcttc.co.kern.ca.us/index.cfm?fuseaction=kcttcinternet.showDefaultedProperty"),
        ("showTaxDefaultedProperties", "https://www.kcttc.co.kern.ca.us/index.cfm?fuseaction=kcttcinternet.showTaxDefaultedProperties"),
        ("showTaxSaleProperties", "https://www.kcttc.co.kern.ca.us/index.cfm?fuseaction=kcttcinternet.showTaxSaleProperties"),
    ]
    for name, url in urls:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        print(f"\n--- {name} ({r.status_code}, {len(r.text)} bytes) ---")
        # Get all meaningful text
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 8]
        for line in lines[:40]:
            print(f"  {line}")
        # Save raw HTML for inspection
        with open(os.path.join(BASE, f"kcttc_{name}.html"), "w", encoding="utf-8") as f:
            f.write(r.text)
        # Look for links to PDF or CSV
        links = soup.find_all("a", href=True)
        for l in links:
            href = l["href"]
            if any(k in href.lower() for k in ["pdf", "csv", "excel", "list", "sale", "default", "auction"]):
                print(f"  LINK: {l.text.strip()} -> {href}")

# ─────────────────────────────────────────────
# SOURCE 3: ASSESSOR co.kern.ca.us (SSL workaround)
# ─────────────────────────────────────────────
def pull_assessor_ssl_bypass():
    print("\n=== KERN COUNTY ASSESSOR (SSL BYPASS) ===")
    urls = [
        "https://assessor.co.kern.ca.us/",
        "http://assessor.co.kern.ca.us/",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=8, verify=False)
            soup = BeautifulSoup(r.text, "html.parser")
            print(f"  {url} -> {r.status_code} | {soup.title.text.strip() if soup.title else 'no title'}")
            links = soup.find_all("a", href=True)
            for l in links:
                if any(k in l.text.lower() or k in l["href"].lower() for k in ["parcel","search","apn","property","roll"]):
                    print(f"    LINK: {l.text.strip()} -> {l['href']}")
        except Exception as e:
            print(f"  {url} -> {e}")

if __name__ == "__main__":
    records = pull_fatco_auction_list()
    if records:
        df = pd.DataFrame(records)
        out = os.path.join(BASE, "kern_REAL_auction_list_fatco.csv")
        df.to_csv(out, index=False)
        print(f"\n*** SAVED REAL KERN AUCTION DATA: {out} ({len(df)} records) ***")
        print(df.head(5).to_string())

    pull_kcttc_taxsale_pages()
    
    import urllib3
    urllib3.disable_warnings()
    pull_assessor_ssl_bypass()
