"""
Test fee parcel API behavior with different APN formats.
"""
import requests, json

HEADERS = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}

# Test: does the API accept partial APNs or just full ones?
tests = [
    # Full APN (with trailing 000)
    "102450028000",
    # Partial - book+page only
    "102450000000",
    # Partial - book only
    "102000000000",
    # Invalid - no such page
    "102999001000",
    # Known valid from Tehama
    "103040024000",
    # Existing discovery APN - a different page in same book 
    "102150007000",
]

print("=== FEE PARCEL API: APN FORMAT TEST ===\n")
for apn in tests:
    url = f"https://common2.mptsweb.com/MBC/api/search/shasta/0000-CURR/feeparcel/{apn}"
    r = requests.get(url, headers=HEADERS, timeout=10)
    try:
        data = json.loads(r.text)
        if isinstance(data, str):
            data = json.loads(data)
        row = data.get("Table", {}).get("Row", {})
        if isinstance(row, list):
            row = row[0] if row else {}
        owner = row.get("OwnerName", "NONE") if row else "NONE"
        situs = row.get("Situs1", "") if row else ""
        print(f"APN {apn:<20} -> Owner: {owner:<30} Situs: {situs}")
    except Exception as e:
        print(f"APN {apn:<20} -> ERROR: {e}")

print("\n=== ASSESSMENT API TEST ===\n")
for apn in ["102450028000", "103040024000"]:
    url = f"https://common2.mptsweb.com/MBC/api/search/shasta/0000-CURR/asmt/{apn}"
    r = requests.get(url, headers=HEADERS, timeout=10)
    try:
        data = json.loads(r.text)
        if isinstance(data, str):
            data = json.loads(data)
        print(f"APN {apn}: {json.dumps(data, indent=2)[:500]}")
    except Exception as e:
        print(f"APN {apn}: ERROR: {e}")

print("\n=== TAX HTML PAGE: BALANCE CHECK ===\n")
for apn in ["102450028000", "061350004000", "60050021000"]:
    url = f"https://common2.mptsweb.com/MBC/shasta/tax/main/{apn}"
    r = requests.get(url, timeout=10)
    if r.status_code == 200:
        html_lower = r.text.lower()
        has_balance = "total balance" in html_lower
        has_delinquent = "delinquent" in html_lower or "late" in html_lower
        # Find balance value
        import re
        balance_match = re.search(r'total balance[^$]*\$?([0-9,]+\.\d{2})', r.text, re.IGNORECASE)
        balance = balance_match.group(1) if balance_match else "N/A"
        print(f"APN {apn:<20} Balance: ${balance:<10} Delinquent: {has_delinquent}")
    else:
        print(f"APN {apn:<20} HTTP {r.status_code}")

print("\n=== DONE ===")
