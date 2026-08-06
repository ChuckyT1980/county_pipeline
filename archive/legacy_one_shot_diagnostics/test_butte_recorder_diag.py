"""
Diagnostic v3: full per-step status/URL/cookies, POST body details,
and search form HTML to check for hidden tokens.
"""
import time
import httpx
from bs4 import BeautifulSoup

client = httpx.Client(
    base_url="https://recorder.buttecounty.net",
    follow_redirects=True,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    },
)
AJAX = {"ajaxrequest": "true", "x-requested-with": "XMLHttpRequest"}

print("=== STEP 1: GET /web/user/disclaimer ===")
r1 = client.get("/web/user/disclaimer")
print(f"Status: {r1.status_code}  Final URL: {r1.url}")
print(f"Cookies after: {dict(client.cookies)}")
time.sleep(0.5)

print()
print("=== STEP 2: POST /web/user/disclaimer ===")
r2 = client.post("/web/user/disclaimer")
print(f"Status: {r2.status_code}  Final URL: {r2.url}")
print(f"Cookies after: {dict(client.cookies)}")
print(f"Body: {r2.text[:100]}")
time.sleep(0.5)

print()
print("=== STEP 3: GET /web/search/DOCSEARCH481S2 ===")
r3 = client.get("/web/search/DOCSEARCH481S2")
print(f"Status: {r3.status_code}  Final URL: {r3.url}")
print(f"Cookies after: {dict(client.cookies)}")
time.sleep(0.5)

# Check search form for hidden tokens
print()
print("=== SEARCH FORM HTML (hidden inputs + form action) ===")
soup3 = BeautifulSoup(r3.text, "html.parser")
for form in soup3.find_all("form"):
    print(f"Form action: {form.get('action')}  method: {form.get('method')}")
    for inp in form.find_all("input"):
        print(f"  <input name={inp.get('name')!r} type={inp.get('type')!r} value={inp.get('value')!r}>")

print()
print("=== STEP 4: POST /web/searchPost/DOCSEARCH481S2 (WITH ajax headers) ===")
r4 = client.post(
    "/web/searchPost/DOCSEARCH481S2",
    data={"field_DocumentNumberID": "2024-0030607", "field_BookPageID_DOT_Volume": "", "field_BookPageID_DOT_Page": ""},
    headers=AJAX,
)
print(f"Status: {r4.status_code}  Final URL: {r4.url}")
print(f"Cookies after: {dict(client.cookies)}")
print(f"Body length: {len(r4.text)}")
print(f"Body (first 500): {r4.text[:500]}")
time.sleep(0.5)

print()
print("=== STEP 5: GET /web/searchResults/DOCSEARCH481S2 (WITH ajax headers) ===")
r5 = client.get("/web/searchResults/DOCSEARCH481S2", params={"page": 1}, headers=AJAX)
print(f"Status: {r5.status_code}  Final URL: {r5.url}")
print(f"ss-search-row: {'ss-search-row' in r5.text}")
print(f"SAUTTER: {'SAUTTER' in r5.text}")
print(f"Body (first 300): {r5.text[:300]}")

client.close()
