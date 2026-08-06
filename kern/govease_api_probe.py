"""
GovEase API — Direct Property Data Pull
GovEase assembled ALL parcel data for bidders: assessed values, tax amounts,
property details, everything. It's public data displayed on their site.
We query their own API the same way their frontend does.
Auction ID 1348 = Kern County Sept 14-16, 2026.
"""
import os, json, time, requests
import pandas as pd
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://liveauctions.govease.com/",
    "Origin": "https://liveauctions.govease.com",
}
BASE = r"C:\Users\chuck\Downloads\county_pipeline\kern"
AUCTION_ID = 1348

# ─── PROBE GOVEASE API ENDPOINTS ──────────────────────────────────
print("=== GOVEASE API ENDPOINT DISCOVERY ===")
api_candidates = [
    f"https://liveauctions.govease.com/api/Auctions/{AUCTION_ID}/Properties",
    f"https://liveauctions.govease.com/api/Auctions/{AUCTION_ID}/Lots",
    f"https://liveauctions.govease.com/api/Auctions/{AUCTION_ID}",
    f"https://liveauctions.govease.com/api/v1/auctions/{AUCTION_ID}/properties",
    f"https://liveauctions.govease.com/api/v1/auctions/{AUCTION_ID}/lots",
    f"https://liveauctions.govease.com/api/Properties?auctionId={AUCTION_ID}",
    f"https://liveauctions.govease.com/api/Lots?auctionId={AUCTION_ID}",
    f"https://liveauctions.govease.com/PublicPortal/GetAuctionProperties?auctionId={AUCTION_ID}",
    f"https://liveauctions.govease.com/PublicPortal/GetProperties?AuctionID={AUCTION_ID}",
    f"https://liveauctions.govease.com/PublicPortal/AuctionProperties?AuctionID={AUCTION_ID}",
    f"https://liveauctions.govease.com/PublicPortal/PropertyList?AuctionID={AUCTION_ID}",
    f"https://govease.com/api/auctions/{AUCTION_ID}/properties",
    f"https://api.govease.com/auctions/{AUCTION_ID}/properties",
    f"https://liveauctions.govease.com/umbraco/api/AuctionApi/GetProperties?auctionId={AUCTION_ID}",
    f"https://liveauctions.govease.com/umbraco/api/PropertyApi/GetByAuction?auctionId={AUCTION_ID}",
]

found_endpoints = []
for url in api_candidates:
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        size = len(r.text)
        ct = r.headers.get("Content-Type","")
        print(f"  [{r.status_code}] {url[:90]}")
        print(f"       Size: {size} | Type: {ct[:50]}")
        if r.status_code == 200 and size > 100:
            try:
                d = r.json()
                print(f"       JSON keys: {list(d.keys())[:8] if isinstance(d,dict) else f'Array len={len(d)}'}")
                found_endpoints.append((url, r.status_code, size, d))
            except Exception:
                if "property" in r.text.lower() or "parcel" in r.text.lower() or "apn" in r.text.lower():
                    print(f"       *** PARCEL DATA IN RESPONSE ***")
                    print(f"       {r.text[:300]}")
                    found_endpoints.append((url, r.status_code, size, r.text))
    except Exception as e:
        print(f"  [ERR] {url[:80]} -> {str(e)[:60]}")

# ─── INSPECT THE REGISTRATION PAGE FOR API CALLS ──────────────────
print("\n=== GOVEASE REGISTRATION PAGE (FIND EMBEDDED API CALLS) ===")
reg_url = f"https://liveauctions.govease.com/PublicPortal/RegistrationDetail?AuctionID={AUCTION_ID}&Edit=False/"
r = requests.get(reg_url, headers=HEADERS, timeout=10)
soup = BeautifulSoup(r.text, "html.parser")

# Extract all JS files referenced
print("JS files loaded:")
for script in soup.find_all("script", src=True):
    src = script.get("src","")
    if src and not src.startswith("http"):
        src = f"https://liveauctions.govease.com{src}"
    print(f"  {src}")

# Find inline API URL references
all_js_text = " ".join([s.string or "" for s in soup.find_all("script") if s.string])
api_refs = []
for pattern in [r'api/[A-Za-z/]+', r'umbraco/api/[A-Za-z/]+', r'/api/v\d+/[A-Za-z/]+']:
    import re
    matches = re.findall(pattern, all_js_text)
    api_refs.extend(matches)

if api_refs:
    print(f"\nAPI references found in page JS ({len(api_refs)}):")
    for ref in sorted(set(api_refs)):
        print(f"  {ref}")

# Extract any JSON data embedded in page
for script in soup.find_all("script"):
    text = script.string or ""
    if "auctionId" in text or "AuctionId" in text or "properties" in text.lower():
        print(f"\nScript with auction data (first 500 chars):")
        print(text[:500])

print("\n=== GOVEASE PROPERTY SEARCH (BY APN) ===")
# Try to look up individual parcels by APN
sample_apns = ["019-053-09-00-9", "123-041-21-00-6", "531-011-21-00-2"]
for apn in sample_apns:
    search_urls = [
        f"https://liveauctions.govease.com/api/Property/Search?apn={apn}&auctionId={AUCTION_ID}",
        f"https://liveauctions.govease.com/api/Properties/Search?q={apn}",
        f"https://liveauctions.govease.com/umbraco/api/PropertyApi/Search?apn={apn}",
    ]
    for url in search_urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=6)
            if r.status_code == 200 and len(r.text) > 50:
                print(f"  [{r.status_code}] {url[:80]}")
                print(f"  Response: {r.text[:300]}")
        except Exception:
            pass
