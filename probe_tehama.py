"""Probe Tehama MPTS portal to understand why discovery returns zero."""
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"}

# 1. Check if Tehama search page loads at all
s = requests.Session()
r0 = s.get("https://common1.mptsweb.com/MBC/tehama/tax/search", timeout=10)
print(f"=== TEHAMA SEARCH PAGE ===")
print(f"HTTP {r0.status_code}, Size: {len(r0.text)}")
title_soup = BeautifulSoup(r0.text, "html.parser")
print(f"Title: {title_soup.title.string if title_soup.title else 'NONE'}")

# 2. Try the search POST
r = s.post("https://common1.mptsweb.com/MBC/tehama/tax/search", 
           data={"SelTaxYear": "2025", "SearchVal": "streetaddress", "SearchValue": "A"},
           headers=HEADERS, timeout=15)
print(f"\n=== TEHAMA SEARCH POST ===")
print(f"HTTP {r.status_code}, Size: {len(r.text)}")
soup = BeautifulSoup(r.text, "html.parser")
print(f"Title: {soup.title.string if soup.title else 'NONE'}")
print(f"ResultDiv: {bool(soup.find(id='ResultDiv'))}")
print(f"Card divs: {len(soup.find_all('div', class_=lambda c: c and 'card' in str(c).lower()))}")
print(f"Tax main links: {len(soup.find_all('a', href=lambda x: x and '/tax/main/' in str(x)))}")

# 3. Same but with Shasta for comparison
s2 = requests.Session()
s2.get("https://common2.mptsweb.com/MBC/shasta/tax/search", timeout=10)
r2 = s2.post("https://common2.mptsweb.com/MBC/shasta/tax/search",
             data={"SelTaxYear": "2025", "SearchVal": "streetaddress", "SearchValue": "A"},
             headers=HEADERS, timeout=15)
print(f"\n=== SHASTA SEARCH POST (for comparison) ===")
print(f"HTTP {r2.status_code}, Size: {len(r2.text)}")
soup2 = BeautifulSoup(r2.text, "html.parser")
print(f"ResultDiv: {bool(soup2.find(id='ResultDiv'))}")
print(f"Card divs: {len(soup2.find_all('div', class_=lambda c: c and 'card' in str(c).lower()))}")
print(f"Tax main links: {len(soup2.find_all('a', href=lambda x: x and '/tax/main/' in str(x)))}")

# Save both for comparison
with open("debug_tehama.html", "w") as f: f.write(r.text)
with open("debug_shasta.html", "w") as f: f.write(r2.text)

# 4. Try the search via GET (maybe POST isn't supported on Tehama)
print(f"\n=== TEHAMA SEARCH GET ===")
r3 = s.get("https://common1.mptsweb.com/MBC/tehama/tax/search", 
           params={"SelTaxYear": "2025", "SearchVal": "streetaddress", "SearchValue": "A"},
           headers=HEADERS, timeout=15)
print(f"HTTP {r3.status_code}, Size: {len(r3.text)}")
soup3 = BeautifulSoup(r3.text, "html.parser")
print(f"Card divs: {len(soup3.find_all('div', class_=lambda c: c and 'card' in str(c).lower()))}")
print(f"Tax main links: {len(soup3.find_all('a', href=lambda x: x and '/tax/main/' in str(x)))}")

# 5. Try fee parcel API directly
api_headers = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
apn_tests = ["103040024000", "073260053000", "60050021000", "013220002000", "007130068000"]
print(f"\n=== TEHAMA FEE PARCEL API ===")
for apn in apn_tests:
    url = f"https://common1.mptsweb.com/MBC/api/search/tehama/0000-CURR/feeparcel/{apn}"
    r = requests.get(url, headers=api_headers, timeout=10)
    if r.status_code == 200:
        import json
        data = json.loads(r.text)
        if isinstance(data, str): data = json.loads(data)
        row = data.get("Table", {}).get("Row", {})
        if isinstance(row, list): row = row[0] if row else {}
        owner = row.get("OwnerName", "NONE") if row else "NONE"
        print(f"APN {apn} -> Owner: {owner}")
    else:
        print(f"APN {apn} -> HTTP {r.status_code}")

print("\n=== DONE ===")
