"""
Look at the raw response from MPTS portal and fee parcel API.
"""
import requests
from bs4 import BeautifulSoup

# 1. RAW HTML from portal search
url = "https://common2.mptsweb.com/MBC/shasta/tax/search"
payload = {"SelTaxYear": "2025", "SearchVal": "streetaddress", "SearchValue": "A"}
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
           "Content-Type": "application/x-www-form-urlencoded"}

# Prime session first
s = requests.Session()
s.get(url, timeout=10)

r = s.post(url, data=payload, headers=headers, timeout=15)
print(f"=== SEARCH RAW RESPONSE (first 2000 chars) ===")
print(f"Status: {r.status_code}, Size: {len(r.text)}")
print(r.text[:2000])

# Check for result patterns
soup = BeautifulSoup(r.text, "html.parser")
print(f"\n=== PARSED SEARCH ===")
print(f"Title: {soup.title.string if soup.title else 'NONE'}")
print(f"ResultDiv: {bool(soup.find(id='ResultDiv'))}")
print(f"ResultsSecton: {bool(soup.find(id='ResultsSecton'))}")
cards = soup.find_all("div", class_=lambda c: c and "card" in str(c).lower())
print(f"Card divs: {len(cards)}")
links = soup.find_all("a", href=lambda x: x and "/tax/main/" in str(x))
print(f"Tax main links: {len(links)}")

# Save full HTML to file for inspection
with open("debug_search.html", "w", encoding="utf-8") as f:
    f.write(r.text)
print("\nSaved full HTML to debug_search.html")

# 2. RAW JSON from fee parcel API
print(f"\n=== FEE PARCEL API RAW RESPONSE ===")
api_url = "https://common2.mptsweb.com/MBC/api/search/shasta/0000-CURR/feeparcel/102450028000"
api_headers = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
r2 = requests.get(api_url, headers=api_headers, timeout=10)
print(f"Status: {r2.status_code}, Size: {len(r2.text)}")
print(f"Content-Type: {r2.headers.get('Content-Type', 'N/A')}")
print(f"Raw (first 1000 chars):")
print(r2.text[:1000])
