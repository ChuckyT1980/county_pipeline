"""Debug owner API response."""
import requests, json

apn = "035470012000"
url = f"https://common1.mptsweb.com/MBC/api/search/tehama/0000-CURR/owner/{apn[:11]}"
r = requests.get(url, headers={
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
}, timeout=10)

print(f"Status: {r.status_code}")
print(f"Content-Type: {r.headers.get('Content-Type')}")
print(f"Raw body: {r.text[:500]}")

try:
    data = r.json()
    print(f"\nJSON type: {type(data).__name__}")
    if isinstance(data, str):
        data = json.loads(data)
        print(f"Double-decoded type: {type(data).__name__}")
    print(f"\nFull JSON:")
    print(json.dumps(data, indent=2)[:1000])
except Exception as e:
    print(f"Error: {e}")
