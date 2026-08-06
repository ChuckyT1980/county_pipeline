"""
Test different MPTS portal search types to find the most comprehensive discovery method.
"""
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

base = "https://common2.mptsweb.com/MBC/shasta/tax/main/"
tehama_base = "https://common1.mptsweb.com/MBC/tehama/tax/main/"

# Test different search types
payloads = [
    # streetaddress search - what we already use
    {"SelTaxYear": "2025", "SearchVal": "streetaddress", "SearchValue": "A"},
    {"SelTaxYear": "2025", "SearchVal": "streetaddress", "SearchValue": "1"},
    # Try owner name search
    {"SelTaxYear": "2025", "SearchVal": "owner", "SearchValue": "SMITH"},
    # Try parcel number search
    {"SelTaxYear": "2025", "SearchVal": "parcelnumber", "SearchValue": "001"},
    # Try fee parcel search
    {"SelTaxYear": "2025", "SearchVal": "feeparcel", "SearchValue": "001"},
    # Try assessor number search
    {"SelTaxYear": "2025", "SearchVal": "asmt", "SearchValue": "001"},
    # Try with blank search
    {"SelTaxYear": "2025", "SearchVal": "streetaddress", "SearchValue": ""},
]

print("=== MPTS SEARCH TYPE PROBE ===\n")

for payload in payloads:
    url = base
    try:
        r = requests.post(url, data=payload, headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
        text = r.text[:300].replace('\n', ' ').replace('\r', '')
        has_results = "card" in r.text.lower() or "fee parcel" in r.text.lower() or "No results" not in r.text[:1000]
        print(f"SearchVal='{payload['SearchVal']:20s}' Value='{payload['SearchValue']:10s}' -> HTTP {r.status_code} Results={has_results} ({len(r.text)} bytes)")
        print(f"  Preview: {text[:150]}")
    except Exception as e:
        print(f"SearchVal='{payload['SearchVal']:20s}' Value='{payload['SearchValue']:10s}' -> ERROR: {e}")
    print()

print("=== TEHAMA SAME TESTS ===\n")

for payload in payloads[:3]:
    try:
        r = requests.post(tehama_base, data=payload, headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
        has_results = "card" in r.text.lower() or "fee parcel" in r.text.lower()
        print(f"TEHAMA SearchVal='{payload['SearchVal']:20s}' Value='{payload['SearchValue']:10s}' -> HTTP {r.status_code} Results={has_results} ({len(r.text)} bytes)")
    except Exception as e:
        print(f"TEHAMA SearchVal='{payload['SearchVal']:20s}' -> ERROR: {e}")
    print()

print("=== DONE ===")
