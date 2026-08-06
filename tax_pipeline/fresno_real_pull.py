"""
Fresno County Real Auction Data Pull
Same approach as Kern - hit FATCO ArcGIS FeatureServer + GovEase + Fresno Tax Collector
"""
import os, re, json, requests
from bs4 import BeautifulSoup
import pandas as pd

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
BASE = r"C:\Users\chuck\Downloads\county_pipeline\fresno"
os.makedirs(BASE, exist_ok=True)

def pull_fatco_fresno():
    print("=== SEARCHING FATCO ARCGIS FOR FRESNO AUCTION LIST ===")
    search_url = "https://www.arcgis.com/sharing/rest/search"
    params = {"q": "Fresno County Auction List tax defaulted", "f": "json", "num": 10,
              "sortField": "numviews", "sortOrder": "desc"}
    r = requests.get(search_url, params=params, headers=HEADERS, timeout=10)
    results = r.json().get("results", [])
    print(f"ArcGIS results: {len(results)}")
    for item in results:
        print(f"  Title: {item.get('title')}")
        print(f"  URL: {item.get('url')}")
        print(f"  Owner: {item.get('owner')}")
    return results

def pull_fresno_endpoints():
    print("\n=== PROBING FRESNO COUNTY TAX COLLECTOR ENDPOINTS ===")
    urls = [
        "https://www.co.fresno.ca.us/departments/treasurer-tax-collector",
        "https://www.co.fresno.ca.us/departments/treasurer-tax-collector/property-tax/defaulted-tax-sale",
        "https://www.fresnocountyca.gov/Departments/Treasurer-Tax-Collector",
        "https://treasurer.fresnocounty.ca.gov/",
        "https://www.fresnocountyca.gov/",
        "https://ttc.fresnocounty.ca.gov/",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=8)
            soup = BeautifulSoup(r.text, "html.parser")
            title = soup.title.text.strip() if soup.title else "no title"
            print(f"  {url} -> {r.status_code} | {title[:70]}")
            if r.status_code == 200:
                links = soup.find_all("a", href=True)
                for l in links:
                    if any(k in l.text.lower() or k in l["href"].lower()
                           for k in ["auction","tax sale","default","govease","bid4assets"]):
                        print(f"    LINK: {l.text.strip()[:60]} -> {l['href'][:80]}")
        except Exception as e:
            print(f"  {url} -> ERROR: {e}")

def pull_govease_fresno():
    print("\n=== PROBING GOVEASE FOR FRESNO AUCTION ===")
    urls = [
        "https://www.govease.com/auctions",
        "https://liveauctions.govease.com/PublicPortal/AuctionList"
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=8)
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text()
            for line in text.split("\n"):
                if "fresno" in line.lower() and len(line.strip()) > 5:
                    print(f"  GOVEASE FRESNO: {line.strip()[:120]}")
            links = soup.find_all("a", href=True)
            for l in links:
                if "fresno" in l.get("href","").lower() or "fresno" in l.text.lower():
                    print(f"  LINK: {l.text.strip()} -> {l['href']}")
        except Exception as e:
            print(f"  {url} -> ERROR: {e}")

def pull_fatco_feature_service(service_url, label):
    print(f"\n=== PULLING: {label} ===")
    info_r = requests.get(f"{service_url}/0?f=json", headers=HEADERS, timeout=10)
    if info_r.status_code == 200:
        info = info_r.json()
        fields = [f["name"] for f in info.get("fields", [])]
        print(f"  Layer: {info.get('name')} | Fields: {len(fields)} | MaxRecords: {info.get('maxRecordCount')}")
        query = requests.get(f"{service_url}/0/query",
            params={"where":"1=1","outFields":"*","f":"json","resultRecordCount":2000,"returnGeometry":"false"},
            headers=HEADERS, timeout=20)
        if query.status_code == 200:
            features = query.json().get("features", [])
            print(f"  Records returned: {len(features)}")
            if features:
                print(f"  Sample: {json.dumps(features[0]['attributes'], indent=2)[:500]}")
                return [f["attributes"] for f in features]
    else:
        print(f"  Status: {info_r.status_code}")
    return []

if __name__ == "__main__":
    # Step 1: Search FATCO for Fresno
    results = pull_fatco_fresno()

    # Step 2: Try known FATCO Fresno URLs (same pattern as Kern)
    fatco_urls = [
        ("https://services.arcgis.com/VYsrLd1WbPJ93eyz/arcgis/rest/services/Fresno_County_Auction_List/FeatureServer", "FATCO Fresno Auction List"),
        ("https://services.arcgis.com/VYsrLd1WbPJ93eyz/arcgis/rest/services/Fresno_County_Auction_List_2026/FeatureServer", "FATCO Fresno 2026"),
        ("https://services.arcgis.com/VYsrLd1WbPJ93eyz/arcgis/rest/services/Fresno_Auction_List/FeatureServer", "FATCO Fresno Alt"),
    ]
    # Also check any Fresno results from the search
    for item in results:
        url = item.get("url","")
        title = item.get("title","")
        if "fresno" in title.lower() and url:
            fatco_urls.append((url.rstrip("/0"), title))

    all_records = []
    for url, label in fatco_urls:
        recs = pull_fatco_feature_service(url, label)
        all_records.extend(recs)

    if all_records:
        df = pd.DataFrame(all_records)
        out = os.path.join(BASE, "fresno_REAL_auction_list_fatco.csv")
        df.to_csv(out, index=False)
        print(f"\n*** SAVED {len(df)} REAL FRESNO RECORDS: {out} ***")
        auction_cols = [c for c in ["Parcel_Number","Owner","Minimum_Bid_Owed","Parcel_Location","Property_Description"] if c in df.columns]
        if auction_cols:
            sub = df[auction_cols].dropna(subset=["Parcel_Number","Minimum_Bid_Owed"] if "Parcel_Number" in df.columns else [])
            print(sub.head(10).to_string())
    else:
        print("\nNo FATCO records found yet - running endpoint probe...")

    pull_fresno_endpoints()
    pull_govease_fresno()
