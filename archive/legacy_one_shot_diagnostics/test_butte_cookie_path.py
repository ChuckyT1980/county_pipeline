"""Test with disclaimerAccepted cookie scoped to /web/ path, matching actual browser cookie path."""
import httpx, time
from bs4 import BeautifulSoup

BASE = "https://recorder.buttecounty.net"
AJAX = {"ajaxrequest": "true", "x-requested-with": "XMLHttpRequest"}

# Use a transport that lets us inspect raw requests
client = httpx.Client(base_url=BASE, follow_redirects=True,
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"})

# Step 1: GET disclaimer — establishes JSESSIONID
client.get("/web/user/disclaimer"); time.sleep(0.3)
print("After GET disclaimer:", dict(client.cookies))

# Step 2: POST disclaimer — server sets disclaimerAccepted on the response
r2 = client.post("/web/user/disclaimer"); time.sleep(0.3)
print("After POST disclaimer:", dict(client.cookies))
print("Set-Cookie headers on POST response:", r2.headers.get("set-cookie"))

# Step 3: GET search page
client.get("/web/search/DOCSEARCH481S2"); time.sleep(0.3)
print("After GET search page:", dict(client.cookies))

# Step 4: POST search
r4 = client.post(
    "/web/searchPost/DOCSEARCH481S2",
    data={"field_DocumentNumberID": "2024-0030607", "field_BookPageID_DOT_Volume": "", "field_BookPageID_DOT_Page": ""},
    headers=AJAX,
)
print(f"POST search: {r4.status_code}  len={len(r4.text)}")
print("After POST search:", dict(client.cookies))

# Check the error message vs something useful
soup = BeautifulSoup(r4.text, "html.parser")
for el in soup.find_all(["h1", "h2", "p"]):
    t = el.get_text(strip=True)
    if t and len(t) > 5:
        print(repr(t))

client.close()
