"""Test name search (DOCSEARCH481S1) against Butte recorder — checks whether
the application error is specific to DOCSEARCH481S2 or affects all searches."""
import time, httpx
from bs4 import BeautifulSoup

BASE = "https://recorder.buttecounty.net"
AJAX = {"ajaxrequest": "true", "x-requested-with": "XMLHttpRequest"}

client = httpx.Client(base_url=BASE, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"})

client.get("/web/user/disclaimer"); time.sleep(0.3)
client.post("/web/user/disclaimer"); time.sleep(0.3)
print("Cookies:", dict(client.cookies))

# Try name search endpoint
client.get("/web/search/DOCSEARCH481S1"); time.sleep(0.3)
r = client.post(
    "/web/searchPost/DOCSEARCH481S1",
    data={
        "field_BothNamesID-searchInput": "SAUTTER",
        "field_BothNamesID-containsInput": "Contains Any",
        "field_BothNamesID": "",
        "field_RecordingDateID_DOT_StartDate": "",
        "field_RecordingDateID_DOT_EndDate": "",
        "field_UseAdvancedSearch": "",
    },
    headers={**AJAX, "Referer": f"{BASE}/web/search/DOCSEARCH481S1"},
)
print(f"Name search POST: {r.status_code}  len={len(r.text)}")
soup = BeautifulSoup(r.text, "html.parser")
for el in soup.find_all(["h1","p","li"]):
    t = el.get_text(strip=True)
    if t and 5 < len(t) < 200:
        print(repr(t))
        break

time.sleep(0.3)
r2 = client.get("/web/searchResults/DOCSEARCH481S1", params={"page": 1}, headers=AJAX)
print(f"Name results: {r2.status_code}  ss-search-row: {'ss-search-row' in r2.text}  SAUTTER: {'SAUTTER' in r2.text}")

client.close()
