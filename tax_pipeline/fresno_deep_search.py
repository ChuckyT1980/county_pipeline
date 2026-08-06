import requests
from bs4 import BeautifulSoup
import json

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}

print("=== GOVEASE FRESNO AUCTION ID SEARCH ===")
for aid in range(1340, 1370):
    url = f"https://liveauctions.govease.com/PublicPortal/RegistrationDetail?AuctionID={aid}&Edit=False/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=5)
        if r.status_code == 200 and len(r.text) > 500:
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text().lower()
            if "fresno" in text or "stanislaus" in text or "merced" in text or "tulare" in text:
                print(f"  AuctionID {aid}: MATCH - {soup.title.text.strip() if soup.title else ''}")
                for line in soup.get_text().split("\n"):
                    line = line.strip()
                    if len(line) > 5 and any(k in line.lower() for k in ["fresno","county","sept","2026","auction","parcel"]):
                        print(f"    {line[:100]}")
    except Exception:
        pass

print("\n=== ARCGIS SEARCH FOR FRESNO AUCTION DATA ===")
r = requests.get("https://www.arcgis.com/sharing/rest/search",
    params={"q": "Fresno County tax sale auction 2026 parcel defaulted", "f": "json", "num": 10},
    headers=HEADERS, timeout=10)
results = r.json().get("results", [])
print(f"Results: {len(results)}")
for item in results:
    print(f"  Title: {item.get('title')}")
    print(f"  URL:   {item.get('url')}")
    print(f"  Owner: {item.get('owner')}")
    print()

print("=== TRYING FRESNO COUNTY OPEN DATA (SOCRATA / ARCGIS HUB) ===")
attempts = [
    "https://data.fresno.gov/api/views",
    "https://hub.arcgis.com/api/v3/datasets?q=fresno+county+parcel+tax&filter[type]=Feature+Layer&page[size]=5",
    "https://gis.fresnocounty.ca.gov/arcgis/rest/services?f=json",
    "https://maps.fresnocounty.ca.gov/arcgis/rest/services?f=json",
]
for url in attempts:
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        print(f"  {url} -> {r.status_code} ({len(r.text)} bytes)")
        if r.status_code == 200:
            try:
                d = r.json()
                if isinstance(d, dict):
                    print(f"  Keys: {list(d.keys())[:6]}")
                    services = d.get("services", [])
                    if services:
                        print(f"  Services: {[s.get('name') for s in services[:8]]}")
                elif isinstance(d, list) and d:
                    print(f"  Items: {len(d)} | First keys: {list(d[0].keys())[:6]}")
            except Exception:
                print(f"  Raw: {r.text[:200]}")
    except Exception as e:
        print(f"  {url} -> ERROR: {e}")
