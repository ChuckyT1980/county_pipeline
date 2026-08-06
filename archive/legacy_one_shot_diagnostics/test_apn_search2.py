"""
Test APN search on MPTS portal - deeper look at results.
"""
import requests
from bs4 import BeautifulSoup
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
}

API_HEADERS = {
    "X-Requested-With": "XMLHttpRequest", 
    "Accept": "application/json"
}

def search_portal(host, slug, search_val, search_value):
    """Search MPTS portal and return parsed results."""
    url = f"https://{host}/MBC/{slug}/tax/search"
    payload = {"SelTaxYear": "2025", "SearchVal": search_val, "SearchValue": search_value}
    r = requests.post(url, data=payload, headers=HEADERS, timeout=15)
    
    parcels = []
    if r.status_code == 200:
        soup = BeautifulSoup(r.text, "html.parser")
        # Find result cards
        cards = soup.find_all("div", class_=lambda c: c and "card" in str(c).lower())
        # Fallback: find links with /tax/main/
        if not cards:
            sections = soup.find_all("div", id=lambda x: x and "Result" in str(x))
            for section in sections:
                links = section.find_all("a", href=lambda x: x and "/tax/main/" in str(x))
                for link in links:
                    parcels.append(link.get_text(strip=True))
        else:
            for card in cards:
                link = card.find("a", href=lambda x: x and "/tax/main/" in str(x))
                if link:
                    text = card.get_text(" ", strip=True)
                    parcels.append(text[:200])
    
    return r.status_code, len(r.text), parcels

# Compare search approaches
print("=== SHASTA: SEARCH APPROACH COMPARISON ===\n")

# 1. Street address "A" 
status, size, parcels = search_portal("common2.mptsweb.com", "shasta", "streetaddress", "A")
print(f"streetaddress=A -> HTTP {status} Size={size} Results={len(parcels)}")
for p in parcels[:3]:
    print(f"  {p}")
    
print()
time.sleep(0.5)

# 2. Parcel number "001" (book prefix)
status, size, parcels = search_portal("common2.mptsweb.com", "shasta", "parcelnumber", "001")
print(f"parcelnumber=001 -> HTTP {status} Size={size} Results={len(parcels)}")
for p in parcels[:3]:
    print(f"  {p}")

print()
time.sleep(0.5)

# 3. Fee parcel "001"
status, size, parcels = search_portal("common2.mptsweb.com", "shasta", "feeparcel", "001")
print(f"feeparcel=001 -> HTTP {status} Size={size} Results={len(parcels)}")
for p in parcels[:3]:
    print(f"  {p}")

print()
time.sleep(0.5)

# 4. What does a known APN search look like?
print("=== SHASTA: FEE PARCEL API - DIRECT APN LOOKUP ===\n")

# Known valid APNs
valid_apns = ["070050072000", "064100031000", "102450028000", "061350004000"]
# Invalid patterns
test_apns = ["001001001000", "999999999000", "000000000000"]

for apn in valid_apns + test_apns:
    url = f"https://common2.mptsweb.com/MBC/api/search/shasta/0000-CURR/feeparcel/{apn}"
    try:
        r = requests.get(url, headers=API_HEADERS, timeout=10)
        data = r.json() if r.status_code == 200 else {"error": r.status_code}
        rows = data.get("Table", {}).get("Row", [])
        if isinstance(rows, dict): rows = [rows]
        owner = rows[0].get("OwnerName", "N/A") if rows else "NO DATA"
        due = rows[0].get("CurrDue", "N/A") if rows else ""
        print(f"APN {apn} -> HTTP {r.status_code} Owner={owner} Due={due}")
    except Exception as e:
        print(f"APN {apn} -> ERROR: {e}")
    time.sleep(0.3)

print("\n=== TEHAMA: FEE PARCEL API ===\n")

tehama_apns = ["103040024000", "073260053000", "001001001000", "999999999000"]
for apn in tehama_apns:
    url = f"https://common1.mptsweb.com/MBC/api/search/tehama/0000-CURR/feeparcel/{apn}"
    try:
        r = requests.get(url, headers=API_HEADERS, timeout=10)
        data = r.json() if r.status_code == 200 else {"error": r.status_code}
        rows = data.get("Table", {}).get("Row", [])
        if isinstance(rows, dict): rows = [rows]
        owner = rows[0].get("OwnerName", "N/A") if rows else "NO DATA"
        due = rows[0].get("CurrDue", "N/A") if rows else ""
        print(f"APN {apn} -> HTTP {r.status_code} Owner={owner} Due={due}")
    except Exception as e:
        print(f"APN {apn} -> ERROR: {e}")
    time.sleep(0.3)

print("\n=== DONE ===")
