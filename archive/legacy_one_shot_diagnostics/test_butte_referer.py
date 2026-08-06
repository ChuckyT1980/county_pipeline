import time, httpx
from bs4 import BeautifulSoup

BASE = "https://recorder.buttecounty.net"
SEARCH_ID = "DOCSEARCH481S2"
AJAX = {"ajaxrequest": "true", "x-requested-with": "XMLHttpRequest"}

client = httpx.Client(base_url=BASE, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"})

client.get("/web/user/disclaimer"); time.sleep(0.3)
client.post("/web/user/disclaimer"); time.sleep(0.3)
client.get(f"/web/search/{SEARCH_ID}"); time.sleep(0.3)

# Add Referer matching what a browser would send after visiting the search form page
r = client.post(
    f"/web/searchPost/{SEARCH_ID}",
    data={"field_DocumentNumberID": "2024-0030607", "field_BookPageID_DOT_Volume": "", "field_BookPageID_DOT_Page": ""},
    headers={**AJAX, "Referer": f"{BASE}/web/search/{SEARCH_ID}"},
)
print(f"POST status: {r.status_code}  Final URL: {r.url}")
print(f"Body length: {len(r.text)}")

soup = BeautifulSoup(r.text, "html.parser")
seen = set()
for el in soup.find_all(["h1","h2","p","li"]):
    t = el.get_text(strip=True)
    if t and 5 < len(t) < 200 and t not in seen:
        seen.add(t)
        print(repr(t))

time.sleep(0.3)
r2 = client.get(f"/web/searchResults/{SEARCH_ID}", params={"page": 1}, headers=AJAX)
print(f"\nResults status: {r2.status_code}")
print(f"ss-search-row: {'ss-search-row' in r2.text}")
print(f"SAUTTER: {'SAUTTER' in r2.text}")
if "ss-search-row" in r2.text:
    print(r2.text[:1000])

client.close()
