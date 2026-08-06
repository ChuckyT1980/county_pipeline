"""
Test APN-based search on MPTS portal to find valid parcel ranges.
"""
import requests
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
}

def test_search(county_host, county_slug, search_val, search_value):
    """Test a search type against the MPTS portal."""
    url = f"https://{county_host}/MBC/{county_slug}/tax/search"
    payload = {"SelTaxYear": "2025", "SearchVal": search_val, "SearchValue": search_value}
    try:
        r = requests.post(url, data=payload, headers=HEADERS, timeout=15)
        has_results = "card" in r.text.lower() or "fee parcel" in r.text.lower()
        count_approx = r.text.lower().count("fee parcel") 
        return r.status_code, has_results, count_approx, len(r.text)
    except Exception as e:
        return -1, False, 0, str(e)

# Test different search types on Shasta
print("=== SHASTA: DIFFERENT SEARCH TYPES ===\n")

tests = [
    ("streetaddress", "A", "street A"),
    ("streetaddress", "1", "street 1"),
    ("parcelnumber", "001", "parcel prefix 001"),
    ("owner", "SMITH", "owner name SMITH"),
    ("feeparcel", "001", "fee parcel prefix"),
]

for search_val, search_value, desc in tests:
    code, found, count, size = test_search("common2.mptsweb.com", "shasta", search_val, search_value)
    print(f"{desc:<30} HTTP {code} Found={found:<5} Cards={count:<3} Size={size}")

print("\n=== SHASTA: APN PREFIX SEARCH ===\n")

# Test searching by book number (first 3 digits of APN)
for book in [1, 5, 10, 18, 31, 35, 61, 64, 70, 73, 75, 91, 97, 102, 107]:
    # Try searching for book number as street address (catches things like "18xx Some St")
    code, found, count, size = test_search("common2.mptsweb.com", "shasta", "parcelnumber", f"{book:03d}")
    print(f"Book {book:03d} as parcelnumber -> HTTP {code} Found={found:<5} Cards={count:<3} Size={size}")
    time.sleep(0.5)

print("\n=== SHASTA: FEE PARCEL DIRECT API CHECK ===\n")

# Instead of portal search, use the fee parcel API directly for APN range probing
api_headers = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}

# Test if fee parcel API returns data for non-existent APNs (to understand error pattern)
for apn in ["001001001000", "999999999000", "050001001000", "100001001000"]:
    url = f"https://common2.mptsweb.com/MBC/api/search/shasta/0000-CURR/feeparcel/{apn}"
    r = requests.get(url, headers=api_headers, timeout=10)
    data = r.json() if r.status_code == 200 else {}
    rows = data.get("Table", {}).get("Row", [])
    has_data = len(rows) > 0 and (isinstance(rows, list) or (isinstance(rows, dict) and rows))
    print(f"APN {apn} -> HTTP {r.status_code} HasData={has_data}")
    time.sleep(0.3)

print("\n=== DONE ===")
