"""Print the exact request headers httpx sends on the search POST for header-by-header diff."""
import httpx, time

BASE = "https://recorder.buttecounty.net"
AJAX = {"ajaxrequest": "true", "x-requested-with": "XMLHttpRequest"}

client = httpx.Client(base_url=BASE, follow_redirects=True,
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"})

client.get("/web/user/disclaimer"); time.sleep(0.3)
client.post("/web/user/disclaimer"); time.sleep(0.3)
client.get("/web/search/DOCSEARCH481S2"); time.sleep(0.3)

r = client.post(
    "/web/searchPost/DOCSEARCH481S2",
    data={"field_DocumentNumberID": "2024-0030607", "field_BookPageID_DOT_Volume": "", "field_BookPageID_DOT_Page": ""},
    headers=AJAX,
)

print("=== EXACT REQUEST HEADERS httpx SENT (search POST) ===")
for k, v in r.request.headers.items():
    print(f"{k}: {v}")

print()
print("=== REQUEST URL ===")
print(r.request.url)

print()
print("=== REQUEST BODY (raw) ===")
print(r.request.content.decode())

print()
print("=== RESPONSE STATUS ===")
print(r.status_code)

client.close()
